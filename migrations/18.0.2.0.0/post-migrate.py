from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    students = env['student.university'].search([])
    # Historical marks stay intact; aggregate values must follow the new publication control.
    for field in ['gpa', 'total_points', 'total_credits']:
        env.add_to_compute(students._fields[field], students)
    students._recompute_recordset(['gpa', 'total_points', 'total_credits'])
