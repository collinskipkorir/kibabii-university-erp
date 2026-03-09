from odoo import http
from odoo.http import request


class UniversityWebsite(http.Controller):

    @http.route('/universities', type='http', auth='public', website=True)
    def universities(self, **kw):
        universities = request.env['university.management'].sudo().search([])

        return request.render(
            'kibabii_university_erp.university_list_template',
            {'universities': universities}
        )


class StudentPortal(http.Controller):

    @http.route('/my/student', type='http', auth='user', website=True)
    def student_dashboard(self, **kw):
        student = request.env['student.university'].search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)

        return request.render(
            'kibabii_university_erp.student_dashboard_template',
            {
                'student': student
            }
        )

    @http.route('/student/register/submit', type='http', auth='public', methods=['POST'], website=True)
    def student_register_submit(self, **post):
        user = request.env['res.users'].sudo().create({
            'name': post.get('name'),
            'login': post.get('email'),
            'email': post.get('email'),
            'password': post.get('password'),
            'groups_id': [(6, 0, [request.env.ref(
                'kibabii_university_erp.group_student').id])]
        })

        request.env['student.university'].sudo().create({
            'name': post.get('name'),
            'email': post.get('email'),
            'user_id': user.id
        })

        return request.redirect('/web/login')

    @http.route('/my/student/dashboard', type='http', auth='user', website=True)
    def student_dashboard(self):
        student = request.env['student.university'].sudo().search([
            ('user_id', '=', request.env.user.id)
        ], limit=1)

        return request.render(
            'kibabii_university_erp.student_dashboard',
            {'student': student}
        )

    @http.route('/my/results', type='http', auth='user', website=True)
    def student_results(self):
        results = request.env['student.result'].sudo().search([
            ('student_id.user_id', '=', request.env.user.id)
        ])

        return request.render(
            'kibabii_university_erp.student_results',
            {'results': results}
        )

    @http.route('/my/transcript/<int:student_id>', type='http', auth='user')
    def download_transcript(self, student_id):
        pdf = request.env.ref(
            'kibabii_university_erp.student_transcript_report'
        )._render_qweb_pdf([student_id])[0]

        return request.make_response(
            pdf,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', 'attachment; filename=transcript.pdf')
            ]
        )

    @http.route('/my/fees', type='http', auth='user', website=True)
    def student_fees(self):
        fees = request.env['university.fee'].sudo().search([
            ('student_id.user_id', '=', request.env.user.id)
        ])

        return request.render(
            'kibabii_university_erp.student_fees',
            {'fees': fees}
        )
