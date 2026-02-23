from odoo import fields, models


class UniversityDepartment(models.Model):
    _name = 'university.department'
    _description = 'University Department'

    name = fields.Char(string="Department Name", required=True)

    department_type = fields.Selection(
        [
            ('registrar', 'Registrar / Admissions'),
            ('finance', 'Finance'),
            ('academic', 'Academic / Lecturers'),
        ],
        string="Department Type",
        required=True
    )

    university_id = fields.Many2one(
        'university.management',
        string="University",
        required=True,
        ondelete='cascade'
    )

    description = fields.Text(string="Responsibilities")