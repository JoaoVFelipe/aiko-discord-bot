import json, os
from engine import discord_actions

async def execute_help(message):
    script_dir = os.path.dirname(__file__)
    filepath = os.path.join(script_dir, '../data/help.json')
    help_data = open_json_file(filepath)

    to_help_command = message.content.split(' ')
    to_help_command.pop(0)
    to_help_command = ' '.join(to_help_command)


    help_message = build_help_message(help_data, to_help_command)

    await discord_actions.send_message(channel=message.channel, message_title=help_message['message_title'], message_fields=help_message['message_fields'])


def build_help_message(help_dict, help_command):
    message_fields = []
    
    if(help_command):
        found_command = False

        for group in help_dict['commands']['groups']:
            for command in group['group_commands']:
                if(command['name'] == help_command):
                    found_command = command
                    break
            
            if found_command:
                break
        
        if found_command:
            message_fields.append(
                 {
                    'message_text': 'Descrição:',
                    'message_description': found_command['description'],
                    'inline': False
                }
            )
            message_fields.append(
                 {
                    'message_text': 'Como usar:',
                    'message_description': found_command['usage'],
                    'inline': False
                }
            )

            formatted_examples = ''
            for example in found_command['examples']:
                formatted_examples = formatted_examples + '**'+example['command']+': **'+'\n'
                formatted_examples = formatted_examples + '- '+example['explanation']+'\n\n'

            message_fields.append(
                 {
                    'message_text': 'Exemplo(s):',
                    'message_description': formatted_examples,
                    'inline': False
                }
            )
            return {
                'message_title': 'Ajuda - Comando '+ found_command['name'],
                'message_fields': message_fields
            }  
        else:
            return {
                'message_title': 'Desculpe, não fui capaz de encontrar este comando :(',
                'message_fields': []
            }    
                
    else:
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

        message_fields.append(
            {
                'message_text': '** **',
                'message_description': 'Digite !help *comando* caso uma explicação de algum comando específico!',
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