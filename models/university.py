from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UniversityManagement(models.Model):
    _name = 'university.management'
    _description = 'University Management'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='University Name')
    location = fields.Char(string='University Location')
    email = fields.Char(string='University Email')
    phone_number = fields.Char(string='University Phone Number')
    student_ids = fields.One2many(
        'student.university',
        'university_id',
        string="Students"
    )
    department_ids = fields.One2many(
        'university.department',
        'university_id',
        string="Departments"
    )
    fee_ids = fields.One2many(
        comodel_name='university.student',
        inverse_name='university_id',
        string="Fees"
    )
    course_ids = fields.One2many(
        'university.course',
        inverse_name='university_id',
        string="Courses"
    )
    result_ids = fields.One2many(
        comodel_name='university.result',
        inverse_name='university_id',
        string="Results"
    )

    @api.constrains('admission_slots_remaining', 'admission_slots_needed')
    def _check_admission_slots(self):
        for record in self:
            if record.admission_slots_remaining < record.admission_slots_needed:
                raise ValidationError('not enough admission slots')

    @api.model_create_multi
    def create(self, vals):
        if not vals.get('code'):
            vals['code'] = self.env['ir.sequence'].next_by_code(
                'university.course'
            )
        return super().create(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('registration_number'):
                vals['registration_number'] = self.env['ir.sequence'].next_by_code(
                    'student.university'
                )
        return super().create(vals_list)

    @api.onchange('student_ids')
    def onchange_student_ids(self):
        if self.student_ids:
            self.student_ids = self.student_ids.filtered()

    @api.modlel_update
    def update(self):
        if self.student_ids:
            self.student_ids = self.student_ids.updated()

    def unlink(self):
        for record in self:
            if record.fee_ids:
                raise ValidationError("Cannot delete student with fee records.")
        return super().unlink()

    fee_ids = fields.One2many('university.fee', 'student_id')
    student_status = fields.Selection([
        ('bonified', 'Bonified'),
        ('unbonified', 'Unbonified'),
    ],
        compute='_compute_student_status',
        store=True,
        tracking=True,
    )

    total_fee = fields.Float(compute='_compute_fee', store=True)
    total_paid = fields.Float(compute='_compute_fee', store=True)
    fee_balance = fields.Float(compute='_compute_fee', store=True)

    fee_status = fields.Selection(
        [
            ('paid', 'Paid'),
            ('partial', 'Partially Paid'),
            ('unpaid', 'Unpaid'),
        ],
        compute='_compute_fee',
        store=True,
        tracking=True
    )

    @api.depends('fee_ids.amount', 'fee_ids.paid_amount')
    def _compute_fee(self):
        for student in self:
            total = sum(f.amount for f in student.fee_ids)
            paid = sum(f.paid_amount for f in student.fee_ids)
            balance = total - paid

            student.total_fee = total
            student.total_paid = paid
            student.fee_balance = balance

            # 🔥 Fee Status Logic
            if total == 0:
                student.fee_status = 'unpaid'
            elif balance <= 0:
                student.fee_status = 'paid'
            elif paid > 0:
                student.fee_status = 'partial'
            else:
                student.fee_status = 'unpaid'

    @api.depends('student_ids.amount', 'student_ids.paid_amount')
    def _compute_student_status(self):
        for student in self:
            total = sum(f.amount for f in student.fee_ids)
            paid = sum(f.paid_amount for f in student.fee_ids)
            balance = total - paid

            student.total_fee = total
            student.total_paid = paid
            student.fee_balance = balance

            if balance == 0:
                return "student is a bonified student"
            else:
                return "non bonified student"
