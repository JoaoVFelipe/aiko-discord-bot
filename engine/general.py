import json, os
from engine import discord_actions

async def execute_help(message):
    script_dir = os.path.dirname(__file__)
    filepath = os.path.join(script_dir, '../data/help.json')
    help_data = open_json_file(filepath)

    to_help_command = message.content.split(' ')
    to_help_command.pop(0)

    help_message = build_help_message(help_data, to_help_command)

    await discord_actions.send_message(message_event=message, message_title=help_message['message_title'], message_fields=help_message['message_fields'])


def build_help_message(help_dict, help_command):
    if(help_command):
        return
    else:
        message_fields = []
        for group in help_dict['commands']['groups']:
            group_commands = []
            for command in group['group_commands']:
                formatted_name = '`'+command['name']+'`'
                group_commands.append(formatted_name)

            message_fields.append(
                {
                    'message_text': group['group_name'],
                    'message_description': ', '.join(group_commands),
                    'inline': False
                }
            )

        return {
            'message_title': 'Aiko Help - Comandos!',
            'message_fields': message_fields
        }       

def open_json_file(file_path):
    with open(file_path, 'r', encoding='utf8') as file:
        data = json.load(file)
        return data