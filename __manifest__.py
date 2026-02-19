{
    'name': 'university erp',
    'version': '1.0',
    'category': 'University',
    'summary': 'University Erp',
    'description': """This is a university erp system meant to manage the university eco-system""",
    'author': 'collins',
    'sequence':'-10',
    'depends': ['base', 'account'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/university_departments_views.xml',
        'views/university_student_views.xml',
        'views/menu.xml',
    ],

    'application': True,
    'installable': True,
    'auto_install': True,
}
