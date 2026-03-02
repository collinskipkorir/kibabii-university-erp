{
    'name': 'University ERP',
    'version': '1.0',
    'category': 'University',
    'summary': 'University ERP',
    'description': """This is a university ERP system meant to manage the university ecosystem""",
    'author': 'Collins',
    'category': 'University',
    'sequence': -10,
    'depends': ['base', 'account'],
    'license': 'LGPL-3',
    'data': [
        # security
        'security/groups.xml',
        'security/ir.model.access.csv',
        'security/university_rules.xml',
        'security/student_rules.xml',

        # module category
        'data/module_category.xml',
        # views
        'views/student_results.xml',
        'views/student_fee.xml',
        'views/student_course.xml',
        'views/university_departments_views.xml',
        'views/university_student_views.xml',
        'views/menu.xml',

        # Report templates
        'reports/university_report.xml',
        'reports/department_reports.xml',
        'reports/student_fee_report.xml',
        'reports/student_list_report.xml',
        'reports/student_result_report.xml',

        'reports/report_action.xml',
    ],
    'application': True,
    'installable': True,
}
