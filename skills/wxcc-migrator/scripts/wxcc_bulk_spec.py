"""
Webex Contact Center Bulk Operations - CSV definitions used by the generator and the validator.

Source: help.webex.com "CSV definition for bulk operations in Webex Contact Center" (imku7e)
and "Bulk Operations in Webex Contact Center" (31e39g). Column order follows the article;
confirm against Control Hub > Contact Center > Bulk Operations > "Download a sample template"
before a production run (template spelling wins).
"""

HEADERS = {
    'skill_definitions': ['Name', 'Description', 'Service Level Threshold', 'Type', 'List Values For Enum'],
    'skill_profiles': ['Name', 'Description', 'Skill Name', 'Skill Values', 'Delete'],
    'multimedia_profiles': ['Name', 'Description', 'Type', 'Voice', 'Chat', 'Email', 'Social'],
    'sites': ['Name', 'Multimedia Profile'],
    'teams': ['Name', 'Site', 'Type', 'Multimedia Profile', 'Skill Profile', 'DN', 'Capacity', 'Desktop Layout'],
    'auxiliary_codes': ['Name', 'Description', 'Default', 'Work Type'],
    'entry_points': ['Name', 'Description', 'Service Level Threshold', 'Timezone', 'Channel Type',
                     'Social Channel Type', 'Asset Name'],
    'entry_point_mappings': ['Dialed Number', 'Entry Point', 'Region'],
    'queues': ['Name', 'Description', 'Channel Type', 'Max Time In Queue', 'Service Level Threshold', 'Timezone',
               'Permit Monitoring', 'Permit Recording', 'Record All Calls', 'Pause or Resume Enabled',
               'Recording Pause Duration', 'Default Music in Queue', 'Routing Type', 'Skill-Based Agent Selection',
               'Distribution Group', 'Distribution Group Seq', 'Group Fallback Time', 'Group Teams'],
    'global_variables': ['Name', 'Description', 'Agent Editable', 'Agent Viewable', 'Variable Type',
                         'Default Value', 'Reportable', 'Desktop Label'],
    'desktop_profiles': ['Name', 'Description', 'Parent Site', 'Screen Popups', 'Last Agent Routing', 'Wrap Up Type',
                         'Auto Wrap Up Time', 'Agent Available After Outdial', 'Allow Auto Wrap Up Extension',
                         'Wrap Up Options', 'Wrap Up Codes', 'Idle Options', 'Idle Codes', 'Transfer Options',
                         'Transfer Targets', 'Buddy Team Option', 'Buddy Teams', 'Consult To Queue',
                         'Outdial Enabled', 'Outdial EP', 'Address Book', 'Dial Plan Enabled', 'Dial Plan',
                         'Outdial ANI', 'DN Validation Option', 'Validation Criteria', 'Agent Statistics',
                         'Queue Statistics Option', 'Selected Queues', 'Logged In Team Statistics',
                         'Team Statistics Option', 'Selected Teams', 'Agent Threshold Alerts Enabled',
                         'Agent Threshold Alerts'],
    'users': ['Email', 'User Profile', 'Contact Center Enabled', 'Site', 'Teams', 'Skill Profile',
              'Desktop Profile', 'Multimedia Profile', 'External Id', 'Default DN'],
}

# Import order (dependencies flow downwards). File prefix = position.
IMPORT_ORDER = ['auxiliary_codes', 'skill_definitions', 'skill_profiles', 'multimedia_profiles', 'sites', 'teams',
                'entry_points', 'entry_point_mappings', 'queues', 'global_variables', 'desktop_profiles', 'users']

ENUMS = {
    ('skill_definitions', 'Type'): {'TEXT', 'PROFICIENCY', 'BOOLEAN', 'ENUM'},
    ('multimedia_profiles', 'Type'): {'BLENDED', 'BLENDED_REALTIME', 'EXCLUSIVE'},
    ('teams', 'Type'): {'AGENT', 'CAPACITY'},
    ('auxiliary_codes', 'Default'): {'ON', 'OFF'},
    ('entry_points', 'Channel Type'): {'TELEPHONY', 'CHAT', 'EMAIL', 'SOCIAL_CHANNEL', 'SOCIAL CHANNEL'},
    ('queues', 'Channel Type'): {'TELEPHONY', 'CHAT', 'EMAIL'},
    ('queues', 'Routing Type'): {'', 'LONGEST_AVAILABLE_AGENT', 'SKILLS_BASED'},
    ('queues', 'Skill-Based Agent Selection'): {'', 'LONGEST_AVAILABLE_AGENT', 'BEST_AVAILABLE_AGENT'},
    ('global_variables', 'Variable Type'): {'BOOLEAN', 'STRING', 'INTEGER', 'DECIMAL', 'DATE TIME'},
    ('global_variables', 'Agent Editable'): {'ON', 'OFF'},
    ('global_variables', 'Agent Viewable'): {'ON', 'OFF'},
    ('global_variables', 'Reportable'): {'ON', 'OFF'},
    ('desktop_profiles', 'Wrap Up Type'): {'MANUAL', 'AUTO'},
    ('users', 'Contact Center Enabled'): {'On', 'Off', 'ON', 'OFF'},
}

ROW_LIMIT = 5000

# Work types that exist in every WxCC tenant (seen in tenant export)
DEFAULT_WORK_TYPES = {'idle': 'Default Idle Work Type', 'wrapup': 'Default Wrapup Work Type'}
