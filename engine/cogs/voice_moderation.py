import asyncio
import discord
import logging
import typing
from discord.ext import commands
from typing import List, Tuple
from engine import discord_actions
from engine.storage.voice_moderation_store import VoiceModerationStore

log = logging.getLogger("aiko.voice_moderation")


class MuteModal(discord.ui.Modal, title="Configuração de Mute"):
    """Modal para configurar duração e motivo do mute."""

    duration_input = discord.ui.TextInput(
        label="Duração (segundos)",
        placeholder="Ex: 30 para 30 segundos (deixe em branco para permanente)",
        required=False,
        max_length=5,
        style=discord.TextStyle.short
    )

    reason_input = discord.ui.TextInput(
        label="Motivo",
        placeholder="Motivo do mute (opcional)",
        required=False,
        max_length=200,
        style=discord.TextStyle.paragraph
    )

    def __init__(self, view: 'VoiceModerationView'):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        """Processa o submit do modal e executa o mute."""
        # Parse duration
        duration = None
        if self.duration_input.value and self.duration_input.value.strip():
            try:
                duration = int(self.duration_input.value.strip())
                if duration <= 0:
                    return await interaction.response.send_message(
                        "⚠️ Duração deve ser um número positivo.",
                        ephemeral=True
                    )
                if duration > 3600:
                    return await interaction.response.send_message(
                        "⚠️ Duração máxima é 3600 segundos (1 hora).",
                        ephemeral=True
                    )
            except ValueError:
                return await interaction.response.send_message(
                    "⚠️ Duração inválida. Use apenas números.",
                    ephemeral=True
                )

        # Get reason
        reason = self.reason_input.value.strip() if self.reason_input.value else None

        # Execute mute with parameters
        await self.view._execute_mute_with_params(interaction, duration, reason)


class VoiceModerationView(discord.ui.View):
    """
    View interativa para moderação de voz com select menu e botões.
    Mostra cargos ao invés de usuários individuais.
    """
    def __init__(self, cog: 'VoiceModeration', ctx: commands.Context, voice_channel: discord.VoiceChannel):
        super().__init__(timeout=300)  # 5 minutos
        self.cog = cog
        self.ctx = ctx
        self.voice_channel = voice_channel
        self.executor_id = ctx.author.id
        self.selected_roles = []  # Mudou de selected_users para selected_roles

    async def update_components(self):
        """Atualiza os componentes da view com os cargos configurados."""
        # Limpar componentes existentes
        self.clear_items()

        # Buscar cargos alvos configurados
        target_role_ids = await self.cog.store.get_target_roles(self.ctx.guild.id)

        role_options = []
        for role_id in target_role_ids:
            role = self.ctx.guild.get_role(role_id)
            if not role:
                continue

            # Contar membros no canal com este cargo
            member_count = sum(
                1 for m in self.voice_channel.members
                if role in m.roles and m.id != self.ctx.bot.user.id
            )

            if member_count > 0:
                role_options.append(
                    discord.SelectOption(
                        label=f"{role.name} ({member_count} usuários)"[:100],
                        value=str(role.id),
                        description=f"Cargo: {role.name}"[:100]
                    )
                )

        # Adicionar select menu se houver cargos
        if role_options:
            # Limitar a 25 opções (limitação do Discord)
            if len(role_options) > 25:
                role_options = role_options[:25]

            select = discord.ui.Select(
                placeholder="Selecione cargo(s) para moderar",
                min_values=1,
                max_values=min(len(role_options), 25),
                options=role_options
            )
            select.callback = self.on_select
            self.add_item(select)

        # Adicionar botões
        mute_button = discord.ui.Button(label="Mute Selected", style=discord.ButtonStyle.danger, emoji="🔇")
        mute_button.callback = self.on_mute
        self.add_item(mute_button)

        unmute_button = discord.ui.Button(label="Unmute Selected", style=discord.ButtonStyle.success, emoji="🔊")
        unmute_button.callback = self.on_unmute
        self.add_item(unmute_button)

        refresh_button = discord.ui.Button(label="Refresh List", style=discord.ButtonStyle.secondary, emoji="🔄")
        refresh_button.callback = self.on_refresh
        self.add_item(refresh_button)

        close_button = discord.ui.Button(label="Close Panel", style=discord.ButtonStyle.secondary, emoji="✖️")
        close_button.callback = self.on_close
        self.add_item(close_button)

    async def on_select(self, interaction: discord.Interaction):
        """Callback quando cargos são selecionados."""
        if interaction.user.id != self.executor_id:
            return await interaction.response.send_message("Apenas quem abriu o painel pode interagir.", ephemeral=True)

        self.selected_roles = interaction.data['values']
        await interaction.response.send_message(f"Selecionados: {len(self.selected_roles)} cargo(s)", ephemeral=True)

    async def on_mute(self, interaction: discord.Interaction):
        """Callback para abrir modal de configuração do mute."""
        if interaction.user.id != self.executor_id:
            return await interaction.response.send_message("Apenas quem abriu o painel pode interagir.", ephemeral=True)

        if not self.selected_roles:
            return await interaction.response.send_message("Selecione pelo menos um cargo primeiro.", ephemeral=True)

        # Mostrar modal ao invés de executar imediatamente
        modal = MuteModal(self)
        await interaction.response.send_modal(modal)

    async def _execute_mute_with_params(
        self,
        interaction: discord.Interaction,
        duration: typing.Optional[int],
        reason: typing.Optional[str]
    ):
        """
        Executa mute com parâmetros fornecidos pelo modal.

        Args:
            interaction: Discord interaction from modal submit
            duration: Duration in seconds (None for permanent)
            reason: Reason for mute (None if not provided)
        """
        # Defer response since mute might take time
        await interaction.response.defer(ephemeral=True)

        # Convert role IDs to integers
        role_ids = [int(rid) for rid in self.selected_roles]

        # Get members by role in channel
        members_by_role = self.cog._get_members_by_roles_in_channel(
            self.voice_channel,
            role_ids
        )

        # Collect all members (no duplicates)
        all_members = set()
        for members_list in members_by_role.values():
            all_members.update(members_list)

        if not all_members:
            return await interaction.followup.send(
                "Nenhum usuário encontrado com os cargos selecionados.",
                ephemeral=True
            )

        # Execute mute
        results = await self.cog._execute_mute_action(
            self.ctx,
            list(all_members),
            True,
            reason or "Via painel interativo"
        )

        # Schedule auto-unmute if duration provided
        if duration and results['success']:
            successful_members = [
                m for m in all_members
                if m.mention in results['success']
            ]

            # Get role objects for scheduling
            roles_to_process = [
                self.ctx.guild.get_role(rid)
                for rid in role_ids
                if self.ctx.guild.get_role(rid)
            ]

            await self.cog._schedule_auto_unmute(
                self.ctx,
                successful_members,
                duration,
                roles_to_process
            )

        # Build feedback message
        success_count = len(results['success'])
        failed_count = len(results['failed'])

        if duration:
            message = f"✅ {success_count} usuário(s) mutado(s) por {duration}s"
        else:
            message = f"✅ {success_count} usuário(s) mutado(s)"

        if failed_count > 0:
            message += f"\n❌ {failed_count} falha(s)"

        await interaction.followup.send(message, ephemeral=True)

        # Update panel
        await self.update_components()
        embed = self._build_panel_embed()
        try:
            await interaction.message.edit(embed=embed, view=self)
        except:
            pass

    async def on_unmute(self, interaction: discord.Interaction):
        """Callback para desmutar usuários dos cargos selecionados."""
        if interaction.user.id != self.executor_id:
            return await interaction.response.send_message("Apenas quem abriu o painel pode interagir.", ephemeral=True)

        if not self.selected_roles:
            return await interaction.response.send_message("Selecione pelo menos um cargo primeiro.", ephemeral=True)

        # Converter IDs de cargos para integers
        role_ids = [int(rid) for rid in self.selected_roles]

        # Buscar membros no canal com esses cargos
        members_by_role = self.cog._get_members_by_roles_in_channel(self.voice_channel, role_ids)

        # Coletar todos os membros (sem duplicatas)
        all_members = set()
        for members_list in members_by_role.values():
            all_members.update(members_list)

        if not all_members:
            return await interaction.response.send_message("Nenhum usuário encontrado com os cargos selecionados.", ephemeral=True)

        # Executar unmute
        results = await self.cog._execute_mute_action(self.ctx, list(all_members), False, "Via painel interativo")

        # Feedback
        success_count = len(results['success'])
        failed_count = len(results['failed'])
        message = f"✅ {success_count} usuário(s) desmutado(s)"
        if failed_count > 0:
            message += f"\n❌ {failed_count} falha(s)"

        await interaction.response.send_message(message, ephemeral=True)

        # Atualizar painel
        await self.update_components()
        embed = self._build_panel_embed()
        try:
            await interaction.message.edit(embed=embed, view=self)
        except:
            pass

    async def on_refresh(self, interaction: discord.Interaction):
        """Callback para atualizar a lista de cargos."""
        if interaction.user.id != self.executor_id:
            return await interaction.response.send_message("Apenas quem abriu o painel pode interagir.", ephemeral=True)

        await self.update_components()
        embed = self._build_panel_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_close(self, interaction: discord.Interaction):
        """Callback para fechar o painel."""
        if interaction.user.id != self.executor_id:
            return await interaction.response.send_message("Apenas quem abriu o painel pode interagir.", ephemeral=True)

        await interaction.response.edit_message(content="Painel fechado.", embed=None, view=None)
        self.stop()

    def _build_panel_embed(self) -> discord.Embed:
        """Constrói o embed do painel mostrando cargos."""
        total_users = len([m for m in self.voice_channel.members if m.id != self.ctx.bot.user.id])

        embed = discord.Embed(
            title="🎙️ Painel de Moderação de Voz por Cargo",
            description=f"Canal: {self.voice_channel.mention}\nUsuários no canal: {total_users}",
            colour=discord.Colour.from_rgb(88, 52, 235)
        )

        # Listar cargos configurados presentes no canal
        import asyncio
        try:
            target_role_ids = asyncio.run(self.cog.store.get_target_roles(self.ctx.guild.id))
        except:
            target_role_ids = []

        if target_role_ids:
            roles_info = []
            for role_id in target_role_ids:
                role = self.ctx.guild.get_role(role_id)
                if not role:
                    continue

                # Contar membros no canal com este cargo
                member_count = sum(
                    1 for m in self.voice_channel.members
                    if role in m.roles and m.id != self.ctx.bot.user.id
                )

                if member_count > 0:
                    roles_info.append(f"{role.mention}: **{member_count}** usuário(s)")

            if roles_info:
                embed.add_field(
                    name="Cargos no canal",
                    value="\n".join(roles_info[:15]) if len(roles_info) <= 15 else "\n".join(roles_info[:15]) + f"\n\n... e mais {len(roles_info) - 15} cargo(s)",
                    inline=False
                )
            else:
                embed.add_field(
                    name="Cargos no canal",
                    value="Nenhum usuário com cargos configurados no canal.",
                    inline=False
                )
        else:
            embed.add_field(
                name="Cargos no canal",
                value="Nenhum cargo alvo configurado.",
                inline=False
            )

        return embed

    async def on_timeout(self):
        """Chamado quando o timeout expira."""
        try:
            await self.message.edit(content="Painel expirado (5 minutos).", embed=None, view=None)
        except:
            pass


class VoiceModeration(commands.Cog):
    """
    Comandos de moderação de voz com permissões configuráveis.
    """
    def __init__(self, bot: commands.Bot, store: VoiceModerationStore):
        self.bot = bot
        self.store = store
        self._active_timed_mutes: typing.Dict[int, typing.Dict[int, asyncio.Task]] = {}

    # ---------- Métodos Auxiliares de Validação ----------

    async def _check_moderator_permission(self, guild_id: int, member: discord.Member) -> bool:
        """
        Verifica se o membro tem permissão para moderar.
        Retorna True se tem manage_guild OU possui cargo moderador.
        """
        if member.guild_permissions.manage_guild:
            return True

        mod_roles = await self.store.get_moderator_roles(guild_id)
        return any(role.id in mod_roles for role in member.roles)

    async def _check_target_valid(self, guild_id: int, target: discord.Member) -> bool:
        """
        Verifica se o alvo é válido para ser moderado.
        Retorna True se possui pelo menos um cargo alvo.
        """
        target_roles = await self.store.get_target_roles(guild_id)
        if not target_roles:
            return False
        return any(role.id in target_roles for role in target.roles)

    def _check_hierarchy(self, executor: discord.Member, target: discord.Member, bot_member: discord.Member) -> Tuple[bool, str]:
        """
        Verifica hierarquia de cargos.
        Retorna: (is_valid, error_message)
        """
        if target.guild.owner_id == target.id:
            return False, "Não é possível moderar o dono do servidor."

        if executor.top_role <= target.top_role and executor.guild.owner_id != executor.id:
            return False, "Sua hierarquia de cargos não permite moderar este usuário."

        if bot_member.top_role <= target.top_role:
            return False, "A hierarquia de cargos do bot não permite esta ação."

        return True, ""

    def _check_voice_state(self, member: discord.Member) -> Tuple[bool, str]:
        """
        Verifica se o membro está em um canal de voz.
        Retorna: (is_in_voice, error_message)
        """
        if not member.voice or not member.voice.channel:
            return False, f"{member.mention} não está em um canal de voz."
        return True, ""

    def _check_same_channel(self, executor: discord.Member, target: discord.Member) -> bool:
        """
        Verifica se executor e alvo estão no mesmo canal de voz.
        """
        if not executor.voice or not target.voice:
            return False
        return executor.voice.channel.id == target.voice.channel.id

    def _get_members_by_roles_in_channel(
        self,
        channel: discord.VoiceChannel,
        role_ids: List[int]
    ) -> dict:
        """
        Retorna dict mapeando role_id -> lista de membros no canal com aquele cargo.
        Ignora o bot.

        Exemplo retorno:
        {
            123456: [Member1, Member2, Member3],
            789012: [Member4]
        }
        """
        result = {}

        for role_id in role_ids:
            members_with_role = []
            for member in channel.members:
                # Ignorar o bot
                if member.id == self.bot.user.id:
                    continue

                # Verificar se membro tem o cargo
                if any(r.id == role_id for r in member.roles):
                    members_with_role.append(member)

            if members_with_role:
                result[role_id] = members_with_role

        return result

    async def _execute_mute_action(self, ctx: commands.Context, members: List[discord.Member], mute: bool, reason: str = None) -> dict:
        """
        Executa a ação de mute/unmute em uma lista de membros.
        Retorna dict com 'success' e 'failed' lists.
        """
        results = {"success": [], "failed": []}
        bot_member = ctx.guild.get_member(self.bot.user.id)

        for member in members:
            try:
                # Validar se alvo tem cargo configurado
                if not await self._check_target_valid(ctx.guild.id, member):
                    results['failed'].append((member.mention, "Não possui cargo configurado para moderação"))
                    continue

                # Validar se está em canal de voz
                is_in_voice, voice_error = self._check_voice_state(member)
                if not is_in_voice:
                    results['failed'].append((member.mention, "Não está em um canal de voz"))
                    continue

                # Validar se está no mesmo canal
                if not self._check_same_channel(ctx.author, member):
                    results['failed'].append((member.mention, "Não está no seu canal de voz"))
                    continue

                # Validar hierarquia
                is_valid, hierarchy_error = self._check_hierarchy(ctx.author, member, bot_member)
                if not is_valid:
                    results['failed'].append((member.mention, hierarchy_error))
                    continue

                # Executar ação
                await member.edit(mute=mute, reason=reason)
                results['success'].append(member.mention)

                # Log
                action = "muted" if mute else "unmuted"
                log.info(f"Guild {ctx.guild.id}: {ctx.author} {action} {member} - Reason: {reason}")

            except discord.Forbidden:
                results['failed'].append((member.mention, "Não tenho permissões para mutar este usuário"))
                log.warning(f"Guild {ctx.guild.id}: Forbidden when trying to mute {member}")
            except discord.HTTPException as e:
                results['failed'].append((member.mention, f"Erro ao comunicar com o Discord: {str(e)}"))
                log.error(f"Guild {ctx.guild.id}: HTTPException when muting {member}: {e}")
            except Exception as e:
                results['failed'].append((member.mention, f"Erro inesperado: {str(e)}"))
                log.exception(f"Guild {ctx.guild.id}: Unexpected error when muting {member}")

        return results

    async def _auto_unmute_task(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: int,
        original_roles: List[discord.Role]
    ):
        """
        Background task that waits and then unmutes a member.

        Args:
            ctx: Original command context
            member: Member to unmute
            duration: How long to wait (seconds)
            original_roles: Roles used in original mute command
        """
        try:
            # Wait for the duration
            await asyncio.sleep(duration)

            # Clean up tracking
            guild_id = ctx.guild.id
            if guild_id in self._active_timed_mutes:
                self._active_timed_mutes[guild_id].pop(member.id, None)

            # Refresh member object (important - state might have changed)
            try:
                member = await ctx.guild.fetch_member(member.id)
            except discord.NotFound:
                log.info(f"Guild {guild_id}: Member {member.id} left server before auto-unmute")
                return

            # Check if still in voice channel
            if not member.voice or not member.voice.channel:
                log.info(f"Guild {guild_id}: Member {member.mention} left voice before auto-unmute")
                return

            # Check if still has target role
            if not await self._check_target_valid(guild_id, member):
                log.info(f"Guild {guild_id}: Member {member.mention} no longer has target role")
                return

            # Perform unmute
            try:
                await member.edit(mute=False, reason=f"Auto-unmute after {duration}s")
                log.info(f"Guild {guild_id}: Auto-unmuted {member.mention} after {duration}s")

            except discord.Forbidden:
                log.warning(f"Guild {guild_id}: No permission to auto-unmute {member.mention}")
            except discord.HTTPException as e:
                log.error(f"Guild {guild_id}: HTTP error during auto-unmute {member.mention}: {e}")
            except Exception as e:
                log.exception(f"Guild {guild_id}: Unexpected error during auto-unmute {member.mention}: {e}")

        except asyncio.CancelledError:
            # Task was cancelled (manual unmute or re-mute)
            log.debug(f"Guild {ctx.guild.id}: Auto-unmute task cancelled for {member.id}")
            raise
        except Exception as e:
            log.exception(f"Guild {ctx.guild.id}: Unexpected error in auto-unmute task: {e}")

    async def _schedule_auto_unmute(
        self,
        ctx: commands.Context,
        members: List[discord.Member],
        duration: int,
        original_roles: List[discord.Role]
    ):
        """
        Schedule automatic unmute after duration seconds.

        Args:
            ctx: Command context
            members: List of members that were muted
            duration: Duration in seconds
            original_roles: The roles that were used for the mute command
        """
        guild_id = ctx.guild.id

        # Ensure guild exists in tracking dict
        if guild_id not in self._active_timed_mutes:
            self._active_timed_mutes[guild_id] = {}

        # Create unmute task for each member
        for member in members:
            # Cancel existing task if present (in case of re-mute)
            if member.id in self._active_timed_mutes[guild_id]:
                self._active_timed_mutes[guild_id][member.id].cancel()

            # Schedule new unmute task
            task = asyncio.create_task(
                self._auto_unmute_task(ctx, member, duration, original_roles)
            )
            self._active_timed_mutes[guild_id][member.id] = task

    # ---------- Comandos de Moderação ----------

    @commands.hybrid_command(name="vmute", description="Muta usuários por cargo no canal de voz")
    async def voice_mute(
        self,
        ctx: commands.Context,
        roles: commands.Greedy[discord.Role] = None,
        duration: typing.Optional[int] = None,
        *,
        reason: str = None
    ):
        """
        Muta TODOS os usuários com os cargos especificados no canal de voz.
        Se não especificar cargo, muta todos os cargos configurados.

        Uso:
          /vmute @Cargo1 @Cargo2 [duração] [motivo]
          /vmute [duração] [motivo]  <- muta todos os cargos configurados
          /vmute @Cargo1 30 spam    <- muta por 30 segundos com motivo
        """
        # Validar duração se fornecida
        if duration is not None:
            if duration <= 0:
                return await ctx.reply("⚠️ A duração deve ser um número positivo de segundos.")

            MAX_DURATION = 3600  # 1 hour
            if duration > MAX_DURATION:
                return await ctx.reply(f"⚠️ Duração máxima é {MAX_DURATION} segundos (1 hora).")

        # Validar se executor está em canal de voz
        is_in_voice, voice_error = self._check_voice_state(ctx.author)
        if not is_in_voice:
            return await ctx.reply("Você precisa estar em um canal de voz para usar este comando.")

        # Validar permissão do executor
        if not await self._check_moderator_permission(ctx.guild.id, ctx.author):
            log.warning(f"Guild {ctx.guild.id}: {ctx.author} attempted vmute without permission")
            return await ctx.reply("Você não possui permissão para usar comandos de moderação de voz.")

        # Obter target_roles configurados
        target_role_ids = await self.store.get_target_roles(ctx.guild.id)
        if not target_role_ids:
            return await ctx.reply("⚠️ Nenhum cargo alvo configurado. Use `/vmodconfig add_target` primeiro.")

        # Determinar quais cargos serão processados
        if not roles:
            # Sem parâmetro → usar TODOS os target_roles
            role_ids_to_process = target_role_ids
            roles_to_process = [ctx.guild.get_role(rid) for rid in role_ids_to_process if ctx.guild.get_role(rid)]
        else:
            # Com parâmetro → validar se estão em target_roles
            roles_to_process = []
            invalid_roles = []

            for role in roles:
                if role.id in target_role_ids:
                    roles_to_process.append(role)
                else:
                    invalid_roles.append(role.mention)

            if invalid_roles:
                return await ctx.reply(f"⚠️ Os seguintes cargos não estão configurados como alvos: {', '.join(invalid_roles)}\nUse `/vmodconfig add_target` para adicioná-los.")

            role_ids_to_process = [r.id for r in roles_to_process]

        if not roles_to_process:
            return await ctx.reply("Nenhum cargo válido encontrado.")

        # Buscar membros no canal com esses cargos
        channel = ctx.author.voice.channel
        members_by_role = self._get_members_by_roles_in_channel(channel, role_ids_to_process)

        if not members_by_role:
            cargo_mentions = ", ".join(r.mention for r in roles_to_process)
            return await ctx.reply(f"Nenhum usuário com os cargos {cargo_mentions} encontrado no canal de voz.")

        # Coletar todos os membros (evitar duplicatas se usuário tem múltiplos cargos)
        all_members = set()
        for members_list in members_by_role.values():
            all_members.update(members_list)

        # Executar mute
        results = await self._execute_mute_action(ctx, list(all_members), True, reason)

        # Agendar auto-unmute se duração foi fornecida
        if duration and results['success']:
            successful_members = [
                m for m in all_members
                if m.mention in results['success']
            ]
            await self._schedule_auto_unmute(
                ctx,
                successful_members,
                duration,
                roles_to_process
            )

        # Construir resposta detalhada
        message_fields = []

        if results['success']:
            # Contar por cargo
            role_counts = {}
            for role_id, members in members_by_role.items():
                role = ctx.guild.get_role(role_id)
                successful_members = [m for m in members if m.mention in results['success']]
                if successful_members:
                    role_counts[role.mention] = len(successful_members)

            if duration:
                success_text = f"{len(results['success'])} usuário(s) mutado(s) por {duration}s"
            else:
                success_text = f"{len(results['success'])} usuário(s) mutado(s)"
            if role_counts:
                role_breakdown = ", ".join([f"{count} com {role}" for role, count in role_counts.items()])
                success_text += f"\n({role_breakdown})"

            message_fields.append({
                "message_text": "✅ Mutados com sucesso",
                "message_description": success_text,
                "inline": False
            })

        if results['failed']:
            failed_text = "\n".join([f"• {mention}: {error}" for mention, error in results['failed']])
            message_fields.append({
                "message_text": "❌ Falhas",
                "message_description": failed_text,
                "inline": False
            })

        await discord_actions.send_message(
            channel=ctx.channel,
            message_title="🔇 Moderação de Voz por Cargo",
            message_fields=message_fields
        )

    @commands.hybrid_command(name="vunmute", description="Desmuta usuários por cargo no canal de voz")
    async def voice_unmute(self, ctx: commands.Context, roles: commands.Greedy[discord.Role] = None, *, reason: str = None):
        """
        Desmuta TODOS os usuários com os cargos especificados no canal de voz.
        Se não especificar cargo, desmuta todos os cargos configurados.

        Uso:
          /vunmute @Cargo1 @Cargo2 [motivo]
          /vunmute [motivo]  <- desmuta todos os cargos configurados
        """
        # Validar se executor está em canal de voz
        is_in_voice, voice_error = self._check_voice_state(ctx.author)
        if not is_in_voice:
            return await ctx.reply("Você precisa estar em um canal de voz para usar este comando.")

        # Validar permissão do executor
        if not await self._check_moderator_permission(ctx.guild.id, ctx.author):
            log.warning(f"Guild {ctx.guild.id}: {ctx.author} attempted vunmute without permission")
            return await ctx.reply("Você não possui permissão para usar comandos de moderação de voz.")

        # Obter target_roles configurados
        target_role_ids = await self.store.get_target_roles(ctx.guild.id)
        if not target_role_ids:
            return await ctx.reply("⚠️ Nenhum cargo alvo configurado. Use `/vmodconfig add_target` primeiro.")

        # Determinar quais cargos serão processados
        if not roles:
            # Sem parâmetro → usar TODOS os target_roles
            role_ids_to_process = target_role_ids
            roles_to_process = [ctx.guild.get_role(rid) for rid in role_ids_to_process if ctx.guild.get_role(rid)]
        else:
            # Com parâmetro → validar se estão em target_roles
            roles_to_process = []
            invalid_roles = []

            for role in roles:
                if role.id in target_role_ids:
                    roles_to_process.append(role)
                else:
                    invalid_roles.append(role.mention)

            if invalid_roles:
                return await ctx.reply(f"⚠️ Os seguintes cargos não estão configurados como alvos: {', '.join(invalid_roles)}\nUse `/vmodconfig add_target` para adicioná-los.")

            role_ids_to_process = [r.id for r in roles_to_process]

        if not roles_to_process:
            return await ctx.reply("Nenhum cargo válido encontrado.")

        # Buscar membros no canal com esses cargos
        channel = ctx.author.voice.channel
        members_by_role = self._get_members_by_roles_in_channel(channel, role_ids_to_process)

        if not members_by_role:
            cargo_mentions = ", ".join(r.mention for r in roles_to_process)
            return await ctx.reply(f"Nenhum usuário com os cargos {cargo_mentions} encontrado no canal de voz.")

        # Coletar todos os membros (evitar duplicatas se usuário tem múltiplos cargos)
        all_members = set()
        for members_list in members_by_role.values():
            all_members.update(members_list)

        # Executar unmute
        results = await self._execute_mute_action(ctx, list(all_members), False, reason)

        # Cancelar tarefas de auto-unmute pendentes
        guild_id = ctx.guild.id
        if guild_id in self._active_timed_mutes:
            for member in all_members:
                if member.id in self._active_timed_mutes[guild_id]:
                    self._active_timed_mutes[guild_id][member.id].cancel()
                    self._active_timed_mutes[guild_id].pop(member.id)
                    log.debug(f"Guild {guild_id}: Cancelled auto-unmute task for {member.mention}")

        # Construir resposta detalhada
        message_fields = []

        if results['success']:
            # Contar por cargo
            role_counts = {}
            for role_id, members in members_by_role.items():
                role = ctx.guild.get_role(role_id)
                successful_members = [m for m in members if m.mention in results['success']]
                if successful_members:
                    role_counts[role.mention] = len(successful_members)

            success_text = f"{len(results['success'])} usuário(s) desmutado(s)"
            if role_counts:
                role_breakdown = ", ".join([f"{count} com {role}" for role, count in role_counts.items()])
                success_text += f"\n({role_breakdown})"

            message_fields.append({
                "message_text": "✅ Desmutados com sucesso",
                "message_description": success_text,
                "inline": False
            })

        if results['failed']:
            failed_text = "\n".join([f"• {mention}: {error}" for mention, error in results['failed']])
            message_fields.append({
                "message_text": "❌ Falhas",
                "message_description": failed_text,
                "inline": False
            })

        await discord_actions.send_message(
            channel=ctx.channel,
            message_title="🔊 Moderação de Voz por Cargo",
            message_fields=message_fields
        )

    # ---------- Comandos de Configuração ----------

    @commands.hybrid_group(name="vmodconfig", description="Configurar moderação de voz", invoke_without_command=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def vmod_config(self, ctx: commands.Context):
        """Grupo de comandos de configuração de moderação de voz."""
        await ctx.reply("Use os subcomandos: `add_moderator`, `remove_moderator`, `add_target`, `remove_target`, `list`")

    @vmod_config.command(name="add_moderator", description="Adiciona cargo que pode moderar voz")
    @commands.has_guild_permissions(manage_guild=True)
    async def add_mod_role(self, ctx: commands.Context, role: discord.Role):
        """Adiciona um cargo à lista de moderadores."""
        await self.store.add_moderator_role(ctx.guild.id, role.id)
        await ctx.reply(f"✅ Cargo {role.mention} adicionado como moderador de voz.")
        log.info(f"Guild {ctx.guild.id}: {ctx.author} added moderator role {role.id}")

    @vmod_config.command(name="remove_moderator", description="Remove cargo moderador")
    @commands.has_guild_permissions(manage_guild=True)
    async def remove_mod_role(self, ctx: commands.Context, role: discord.Role):
        """Remove um cargo da lista de moderadores."""
        removed = await self.store.remove_moderator_role(ctx.guild.id, role.id)
        if removed:
            await ctx.reply(f"✅ Cargo {role.mention} removido da lista de moderadores.")
            log.info(f"Guild {ctx.guild.id}: {ctx.author} removed moderator role {role.id}")
        else:
            await ctx.reply(f"⚠️ O cargo {role.mention} não estava na lista de moderadores.")

    @vmod_config.command(name="add_target", description="Adiciona cargo que pode ser mutado")
    @commands.has_guild_permissions(manage_guild=True)
    async def add_target_role(self, ctx: commands.Context, role: discord.Role):
        """Adiciona um cargo à lista de alvos."""
        await self.store.add_target_role(ctx.guild.id, role.id)
        await ctx.reply(f"✅ Cargo {role.mention} adicionado como alvo de moderação.")
        log.info(f"Guild {ctx.guild.id}: {ctx.author} added target role {role.id}")

    @vmod_config.command(name="remove_target", description="Remove cargo alvo")
    @commands.has_guild_permissions(manage_guild=True)
    async def remove_target_role(self, ctx: commands.Context, role: discord.Role):
        """Remove um cargo da lista de alvos."""
        removed = await self.store.remove_target_role(ctx.guild.id, role.id)
        if removed:
            await ctx.reply(f"✅ Cargo {role.mention} removido da lista de alvos.")
            log.info(f"Guild {ctx.guild.id}: {ctx.author} removed target role {role.id}")
        else:
            await ctx.reply(f"⚠️ O cargo {role.mention} não estava na lista de alvos.")

    @vmod_config.command(name="list", description="Lista configurações de moderação de voz")
    @commands.has_guild_permissions(manage_guild=True)
    async def list_config(self, ctx: commands.Context):
        """Lista as configurações atuais de moderação de voz."""
        mod_roles = await self.store.get_moderator_roles(ctx.guild.id)
        target_roles = await self.store.get_target_roles(ctx.guild.id)

        # Formatar cargos moderadores
        if mod_roles:
            mod_mentions = []
            for role_id in mod_roles:
                role = ctx.guild.get_role(role_id)
                if role:
                    mod_mentions.append(role.mention)
                else:
                    mod_mentions.append(f"<@&{role_id}> (não encontrado)")
            mod_text = "\n".join(f"• {m}" for m in mod_mentions)
        else:
            mod_text = "Nenhum cargo configurado (apenas admins podem moderar)"

        # Formatar cargos alvos
        if target_roles:
            target_mentions = []
            for role_id in target_roles:
                role = ctx.guild.get_role(role_id)
                if role:
                    target_mentions.append(role.mention)
                else:
                    target_mentions.append(f"<@&{role_id}> (não encontrado)")
            target_text = "\n".join(f"• {m}" for m in target_mentions)
        else:
            target_text = "Nenhum cargo configurado"

        # Enviar embed
        await discord_actions.send_message(
            channel=ctx.channel,
            message_title="⚙️ Configurações de Moderação de Voz",
            message_fields=[
                {
                    "message_text": "🛡️ Cargos Moderadores",
                    "message_description": mod_text,
                    "inline": False
                },
                {
                    "message_text": "🎯 Cargos que podem ser mutados",
                    "message_description": target_text,
                    "inline": False
                }
            ]
        )

    # ---------- Interface Visual ----------

    @commands.hybrid_command(name="vmodpanel", description="Abre painel interativo de moderação de voz")
    async def vmod_panel(self, ctx: commands.Context, channel: discord.VoiceChannel = None):
        """
        Abre um painel interativo para moderação de voz.

        Uso: /vmodpanel [canal]
        Se não especificar canal, usa o canal de voz do executor.
        """
        # Validar permissão do executor
        if not await self._check_moderator_permission(ctx.guild.id, ctx.author):
            return await ctx.reply("Você não possui permissão para usar comandos de moderação de voz.")

        # Determinar canal de voz
        if channel is None:
            is_in_voice, voice_error = self._check_voice_state(ctx.author)
            if not is_in_voice:
                return await ctx.reply("Você precisa estar em um canal de voz ou especificar um canal.")
            channel = ctx.author.voice.channel

        # Verificar se target_roles está configurado
        target_roles = await self.store.get_target_roles(ctx.guild.id)
        if not target_roles:
            return await ctx.reply("⚠️ Nenhum cargo alvo configurado. Use `/vmodconfig add_target` primeiro.")

        # Criar view
        view = VoiceModerationView(self, ctx, channel)
        await view.update_components()
        embed = view._build_panel_embed()

        # Enviar mensagem com view
        message = await ctx.send(embed=embed, view=view)
        view.message = message

    def cog_unload(self):
        """Clean up tasks when cog is unloaded."""
        for guild_tasks in self._active_timed_mutes.values():
            for task in guild_tasks.values():
                task.cancel()
        log.info("VoiceModeration cog unloaded, cancelled all auto-unmute tasks")


async def setup(bot: commands.Bot):
    """Função de setup do cog."""
    store = VoiceModerationStore()
    await bot.add_cog(VoiceModeration(bot, store))
