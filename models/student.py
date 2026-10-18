from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UniversityStudent(models.Model):
    _name = 'student.university'
    _description = 'University Student'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'name'


    name = fields.Char(
        required=True,
        string="Student Name",
        tracking=True
    )

    email = fields.Char(
        required=True,
        string="Student Email"
    )

    phone_number = fields.Char(
        required=True,
        string="Student Phone Number"
    )

    gender = fields.Selection(
        [('male', 'Male'), ('female', 'Female')],
        string="Gender"
    )

    date_of_admission = fields.Date(string="Date of Admission")

    registration_number = fields.Char(
        string="Registration Number",
        readonly=True,
        copy=False,
        default="New"
    )

    university_id = fields.Many2one(
        'university.management',
        string="University",
        ondelete='cascade',
        required=True
    )

    course_id = fields.Many2one(
        'university.course',
        string="Course"
    )

    fee_ids = fields.One2many(
        'university.fee',
        'student_id',
        string="Fees"
    )

    result_ids = fields.One2many(
        'student.result',
        'student_id',
        string="Results"
    )

    total_fee = fields.Float(
        compute='_compute_fee',
        store=True
    )

    total_paid = fields.Float(
        compute='_compute_fee',
        store=True
    )

    fee_balance = fields.Float(
        compute='_compute_fee',
        store=True
    )

    user_id = fields.Many2one(
        'res.users',
        string="Portal User",
        help="User linked to this student"
    )

    fee_status = fields.Selection(
        [
            ('paid', 'Paid'),
            ('partial', 'Partially Paid'),
            ('unpaid', 'Unpaid'),
        ],
        compute='_compute_fee',
        store=True
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

            if total == 0:
                student.fee_status = 'unpaid'
            elif balance <= 0:
                student.fee_status = 'paid'
            elif paid > 0:
                student.fee_status = 'partial'
            else:
                student.fee_status = 'unpaid'

    #grade calculation
    total_credits = fields.Float(
        compute='_compute_gpa',
        store=True
    )
    #points scored
    total_points = fields.Float(
        compute='_compute_gpa',
        store=True
    )

    gpa = fields.Float(
        compute='_compute_gpa',
        store=True
    )

    @api.depends('result_ids.state', 'result_ids.grade_point', 'result_ids.credit_units', 'result_ids.marks')
    def _compute_gpa(self):
        for student in self:
            best = {}
            for result in student.result_ids.filtered(lambda r: r.state == 'published'):
                if result.course_id.id not in best or result.marks > best[result.course_id.id].marks:
                    best[result.course_id.id] = result
            student.total_credits = sum(r.credit_units for r in best.values())
            student.total_points = sum(r.grade_point * r.credit_units for r in best.values())
            student.gpa = student.total_points / student.total_credits if student.total_credits else 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('registration_number', 'New') == 'New':
                vals['registration_number'] = self.env['ir.sequence'].next_by_code(
                    'student.university'
                ) or 'New'
            if vals.get('email') and not vals.get('user_id'):
                login = vals['email'].strip().lower()
                if self.env['res.users'].sudo().with_context(active_test=False).search_count([('login', '=', login)]):
                    raise ValidationError('A user with this email already exists. Select the existing Portal User.')
                user = self.env['res.users'].sudo().with_context(no_reset_password=True).create({
                    'name': vals.get('name'),
                    'login': login,
                    'email': login,
                    'groups_id': [(6, 0, [self.env.ref('kibabii-university-erp.group_student').id])],
                })
                vals['user_id'] = user.id
        return super().create(vals_list)

    @api.constrains('email')
    def _check_email_unique(self):
        for rec in self:
            if rec.email and self.search_count([('email', '=', rec.email), ('id', '!=', rec.id)]) > 0:
                raise ValidationError("Email must be unique for each student.")
