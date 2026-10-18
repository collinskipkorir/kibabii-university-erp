import base64
from datetime import datetime, time, timedelta
from importlib import import_module

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.addons.website.tools import MockRequest
from werkzeug.exceptions import NotFound

M = 'kibabii-university-erp'


@tagged('procedure_seven', 'post_install', '-at_install')
class TestProcedureSeven(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, lang='en_US', mail_notify_force_send=False, mail_create_nosubscribe=True))
        cls.today = fields.Date.today()
        cls.users = {}
        for role in ['registrar', 'coordinator', 'lecturer', 'exam_board', 'finance_officer', 'library_officer']:
            cls.users[role] = cls.env['res.users'].with_context(no_reset_password=True).create({
                'name': 'P7 ' + role, 'login': 'p7-' + role + '@example.invalid',
                'groups_id': [(6, 0, [cls.env.ref(M + '.group_' + role).id])],
            })
        cls.other_lecturer = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Unassigned Lecturer', 'login': 'p7-unassigned@example.invalid',
            'groups_id': [(6, 0, [cls.env.ref(M + '.group_lecturer').id])],
        })
        cls.uni = cls.env['university.management'].create({'name': 'P7 University'})
        cls.department = cls.env['university.department'].create({'name': 'P7 Department', 'department_type': 'academic', 'university_id': cls.uni.id})
        cls.year = cls.env['university.academic.year'].create({'name': 'P7 Academic Year', 'date_start': cls.today - timedelta(days=180), 'date_end': cls.today + timedelta(days=180)})
        cls.semester = cls.env['university.semester'].create({'name': 'P7 Semester', 'year_id': cls.year.id, 'date_start': cls.today - timedelta(days=30), 'date_end': cls.today + timedelta(days=60), 'registration_start': cls.today - timedelta(days=10), 'registration_end': cls.today + timedelta(days=10)})
        cls.policy = cls.env['university.academic.policy'].with_user(cls.users['registrar']).create({'name': 'P7 Policy', 'version': '1'})
        cls.policy.action_approve()
        cls.course = cls.env['university.course'].create({'name': 'P7 Course', 'university_id': cls.uni.id, 'department_id': cls.department.id, 'credit_units': 3})
        cls.programme = cls.env['university.programme'].with_user(cls.users['registrar']).create({'name': 'P7 Programme', 'code': 'P7', 'department_id': cls.department.id, 'coordinator_id': cls.users['coordinator'].id, 'required_credits': 3, 'duration_years': 1, 'policy_id': cls.policy.id, 'course_ids': [(6, 0, cls.course.ids)]})
        cls.students = cls.env['student.university'].create([{
            'name': 'P7 Student ' + suffix, 'email': 'p7-student-' + suffix + '@example.invalid',
            'phone_number': '0700000000', 'university_id': cls.uni.id, 'date_of_birth': '2000-01-01',
            'nationality_id': cls.env.ref('base.ke').id, 'identity_number': 'P7-' + suffix,
            'identity_type': 'national_id', 'programme_id': cls.programme.id,
            'academic_year_id': cls.year.id, 'intake': 'P7 Intake',
            'emergency_name': 'Emergency Contact', 'emergency_phone': '0711111111',
            'entry_qualification': 'P7 qualification',
        } for suffix in ['alice', 'bob']])
        for student in cls.students:
            for kind in ['identity', 'qualification']:
                doc = cls.env['university.student.document'].with_user(cls.users['registrar']).create({
                    'name': kind, 'student_id': student.id, 'kind': kind, 'filename': kind+'.pdf',
                    'file_data': base64.b64encode(b'%PDF-1.4\n%%EOF'),
                })
                doc.action_verify()
            student = student.with_user(cls.users['registrar'])
            student.action_submit_application()
            student.action_verify_application()
            student.action_admit()
            student.action_confirm_registration()
        cls.alice, cls.bob = cls.students
        cls.offering = cls.env['university.course.offering'].with_user(cls.users['registrar']).create({
            'course_id': cls.course.id, 'programme_id': cls.programme.id, 'semester_id': cls.semester.id,
            'lecturer_id': cls.users['lecturer'].id, 'policy_id': cls.policy.id, 'capacity': 2,
        })
        cls.offering.action_open()
        cls.registrations = cls.env['university.course.registration'].with_user(cls.users['registrar']).create([{'student_id': s.id, 'offering_id': cls.offering.id} for s in cls.students])
        cls.registrations.action_submit()
        cls.registrations.action_approve()
        cls.session = cls.env['university.class.session'].with_user(cls.users['registrar']).create({
            'name': 'P7 Class', 'offering_id': cls.offering.id, 'venue': 'P7 Room',
            'start_datetime': datetime.combine(cls.today - timedelta(days=1), time(8)),
            'end_datetime': datetime.combine(cls.today - timedelta(days=1), time(10)),
        })
        cls.session.action_publish()
        cls.session.with_user(cls.users['lecturer']).action_prepare_attendance()
        cls.session.with_user(cls.users['lecturer']).attendance_ids.write({'status': 'present'})
        cls.session.with_user(cls.users['lecturer']).action_complete()

    def _publish_results(self):
        results = self.env['student.result'].with_user(self.users['lecturer']).create([
            {'registration_id': reg.id, 'ca_mark': 80, 'exam_mark': 70} for reg in self.registrations
        ])
        results.action_submit()
        results.with_user(self.users['coordinator']).write({'moderation_note': 'Complete, checked against source marks.'})
        results.with_user(self.users['coordinator']).action_moderate()
        results.with_user(self.users['exam_board']).action_approve()
        results.with_user(self.users['registrar']).action_publish()
        return results.sudo()

    def test_full_registration_and_result_publication(self):
        self.assertEqual(self.alice.registration_state, 'registered')
        self.assertTrue(self.alice.admission_number)
        self.assertNotEqual(self.alice.admission_number, self.bob.admission_number)
        self.assertEqual(self.registrations[0].attendance_rate, 100)
        results = self._publish_results()
        self.assertEqual(results[0].marks, 73)
        self.assertEqual(results[0].grade, 'A')
        self.assertEqual(self.alice.published_credits, 3)
        self.assertEqual(self.alice.gpa, 4)
        visible = self.env['student.result'].with_user(self.alice.user_id).search([])
        self.assertEqual(visible.ids, results.filtered(lambda r: r.student_id == self.alice).ids)
        self.assertTrue(self.env['university.academic.audit'].search_count([('model_name', '=', 'student.result'), ('action', '=', 'Results published')]))

    def test_no_unapproved_publication_or_direct_state_bypass(self):
        result = self.env['student.result'].with_user(self.users['lecturer']).create({'registration_id': self.registrations[0].id, 'ca_mark': 80, 'exam_mark': 70})
        self.assertFalse(self.env['student.result'].with_user(self.alice.user_id).search([]))
        self.assertEqual(self.alice.gpa, 0)
        with self.assertRaises(UserError):
            result.with_user(self.users['registrar']).action_publish()
        with self.assertRaises(AccessError):
            result.write({'state': 'published'})
        with self.assertRaises(AccessError):
            self.alice.write({'registration_state': 'graduated'})
        with self.assertRaises(AccessError):
            self.env['student.result'].create({'registration_id': self.registrations[0].id, 'state': 'published'})

    def test_lecturer_assignment_and_student_privacy(self):
        result = self.env['student.result'].with_user(self.users['lecturer']).create({'registration_id': self.registrations[0].id})
        with self.assertRaises(AccessError):
            result.with_user(self.other_lecturer).read(['marks'])
        with self.assertRaises(AccessError):
            self.alice.with_user(self.bob.user_id).read(['name'])
        with self.assertRaises(AccessError):
            self.session.with_user(self.other_lecturer).action_prepare_attendance()
        with self.assertRaises(AccessError):
            self.alice.with_user(self.alice.user_id).write({'name': 'Unauthorized edit'})
        with self.assertRaises(AccessError):
            self.alice.with_user(self.users['lecturer']).read(['identity_number'])

    def test_attendance_correction_and_absence_routing(self):
        line = self.session.attendance_ids.filtered(lambda a: a.student_id == self.alice)
        with self.assertRaises(AccessError):
            line.with_user(self.users['lecturer']).write({'status': 'absent', 'correction_reason': 'Wrong initial mark'})
        with self.assertRaises(ValidationError):
            line.with_user(self.users['coordinator']).write({'status': 'absent'})
        line.with_user(self.users['coordinator']).write({'status': 'absent', 'correction_reason': 'Verified attendance sheet correction'})
        registration = self.registrations.filtered(lambda r: r.student_id == self.alice)
        self.assertTrue(registration.absence_flag)
        registration.with_user(self.users['lecturer']).action_flag_absence()
        registration.with_user(self.users['lecturer']).action_flag_absence()
        self.assertEqual(self.env['mail.activity'].search_count([('res_model', '=', 'student.university'), ('res_id', '=', self.alice.id)]), 1)
        result = self.env['student.result'].with_user(self.users['lecturer']).create({'registration_id': registration.id, 'ca_mark': 80, 'exam_mark': 70})
        with self.assertRaises(UserError):
            result.action_submit()

    def test_timetable_conflict_and_policy_freeze(self):
        conflict = self.env['university.class.session'].with_user(self.users['registrar']).create({
            'name': 'Conflicting class', 'offering_id': self.offering.id, 'venue': 'P7 Room',
            'start_datetime': self.session.start_datetime, 'end_datetime': self.session.end_datetime,
        })
        with self.assertRaises(ValidationError):
            conflict.action_publish()
        with self.assertRaises(UserError):
            self.policy.write({'pass_mark': 20})
        copy = self.policy.copy()
        self.assertEqual(copy.state, 'draft')
        self.assertEqual(copy.version, '2')
        with self.assertRaises(UserError):
            self.course.write({'credit_units': 9})

    def test_marks_completeness_and_moderation(self):
        result = self.env['student.result'].with_user(self.users['lecturer']).create({'registration_id': self.registrations[0].id, 'ca_mark': 80})
        with self.assertRaises(UserError):
            result.action_submit()
        result.write({'exam_mark': 70})
        result.action_submit()
        with self.assertRaises(UserError):
            result.with_user(self.users['exam_board']).action_approve()
        with self.assertRaises(UserError):
            result.write({'exam_mark': 99})

    def test_graduation_progression_and_separate_clearances(self):
        results = self._publish_results()
        progression = self.env['university.progression'].with_user(self.users['coordinator']).create({
            'student_id': self.alice.id, 'semester_id': self.semester.id, 'policy_id': self.policy.id,
        })
        progression.action_evaluate()
        progression.with_user(self.users['exam_board']).action_approve()
        self.assertEqual(progression.decision, 'progress')
        with self.assertRaises(UserError):
            self.alice.with_user(self.users['registrar']).action_graduate()
        fee = self.env['university.fee'].create({'name': 'Tuition', 'student_id': self.alice.id, 'amount': 1000})
        for kind, officer in [('academic','registrar'),('financial','finance_officer'),('library','library_officer')]:
            clearance = self.env['university.student.clearance'].with_user(self.users[officer]).create({'student_id': self.alice.id, 'kind': kind, 'notes': 'Source evidence reviewed.'})
            if kind == 'financial':
                with self.assertRaises(UserError):
                    clearance.action_clear()
                fee.write({'paid_amount': 1000})
            clearance.action_clear()
        self.alice.with_user(self.users['registrar']).action_graduate()
        self.assertEqual(self.alice.registration_state, 'graduated')
        self.assertTrue(self.alice.graduation_eligible)

    def test_appeal_and_audited_amendment(self):
        result = self._publish_results()[0]
        progression = self.env['university.progression'].create({'student_id':result.student_id.id,'semester_id':self.semester.id,'policy_id':self.policy.id})
        progression.action_evaluate()
        progression.action_approve()
        clearance=self.env['university.student.clearance'].create({'student_id':result.student_id.id,'kind':'academic','notes':'Academic requirements confirmed.'})
        clearance.action_clear()
        appeal = self.env['university.academic.appeal'].create({'result_id': result.id, 'reason': 'Please review the CA component.'})
        self.assertEqual(appeal.student_id, result.student_id)
        self.assertFalse(self.env['university.academic.appeal'].with_user(self.bob.user_id).search([('id', '=', appeal.id)]))
        appeal.with_user(self.users['exam_board']).write({'resolution': 'Confirmed entry correction required.'})
        appeal.with_user(self.users['exam_board']).action_resolve()
        result.with_user(self.users['registrar']).write({'amendment_reason': 'Source CA sheet verified after appeal.'})
        result.with_user(self.users['registrar']).action_reopen()
        self.assertEqual(result.state, 'draft')
        self.assertEqual(result.revision, 2)
        self.assertEqual(progression.state,'draft')
        self.assertEqual(clearance.state,'draft')
        self.assertFalse(self.env['student.result'].with_user(result.student_id.user_id).search([('id', '=', result.id)]))

    def test_portal_pages_and_reports_render(self):
        self._publish_results()
        website = self.env['website'].search([],limit=1)
        env = self.env(user=self.alice.user_id)
        portal = import_module('odoo.addons.'+M+'.controllers.student_portal').AcademicStudentPortal()
        with MockRequest(env,website=website,url_root='http://localhost:8069/') as request:
            values = portal._profile_values(self.alice.with_user(self.alice.user_id))
            cases=[('academic_student_profile',values),('academic_student_courses',{'student':self.alice.with_user(self.alice.user_id),'offerings':self.offering.sudo(),'error':False}),('academic_student_timetable',{'student':self.alice,'sessions':self.session}),('academic_student_attendance',{'student':self.alice.with_user(self.alice.user_id),'registrations':self.registrations[:1].with_user(self.alice.user_id)}),('academic_student_appeals',{'student':self.alice,'results':self.alice.published_result_ids,'appeals':self.env['university.academic.appeal'],'error':False})]
            for template,values in cases:
                self.assertTrue(env['ir.ui.view']._render_template(M+'.'+template,values))
            with self.assertRaises(NotFound):
                portal.download_transcript(self.bob.id)
        with MockRequest(self.env,website=website,url_root='http://localhost:8069/'):
            for action,records in [('action_graduation_eligibility',self.alice),('action_class_attendance',self.session),('student_transcript_report',self.alice)]:
                html,_=self.env['ir.actions.report']._render_qweb_html(M+'.'+action,records.ids)
                self.assertTrue(html)

    def _new_student(self, suffix, programme=None):
        student = self.env['student.university'].create({
            'name': 'Candidate ' + suffix, 'email': 'p7-' + suffix + '@example.invalid',
            'phone_number': '0722222222', 'university_id': self.uni.id, 'date_of_birth': '2000-02-01',
            'nationality_id': self.env.ref('base.ke').id, 'identity_number': 'P7-EXTRA-' + suffix,
            'programme_id': (programme or self.programme).id, 'academic_year_id': self.year.id,
            'intake': 'P7', 'emergency_name': 'Parent', 'emergency_phone': '0733333333',
            'entry_qualification': 'School Certificate',
        })
        for kind in ['identity', 'qualification']:
            self.env['university.student.document'].with_user(self.users['registrar']).create({
                'student_id': student.id, 'name': kind, 'kind': kind, 'filename': 'test.pdf',
                'file_data': base64.b64encode(b'%PDF-1.4\n%%EOF'),
            }).action_verify()
        registrar_student = student.with_user(self.users['registrar'])
        registrar_student.action_submit_application()
        registrar_student.action_verify_application()
        registrar_student.action_admit()
        registrar_student.action_confirm_registration()
        return student

    def test_registration_capacity_and_prerequisites(self):
        student = self._new_student('capacity')
        registration = self.env['university.course.registration'].create({'student_id': student.id, 'offering_id': self.offering.id})
        with self.assertRaises(ValidationError):
            registration.action_submit()
        advanced = self.env['university.course'].create({'name': 'Advanced P7', 'credit_units': 3, 'university_id': self.uni.id, 'department_id': self.department.id, 'prerequisite_ids': [(6,0,self.course.ids)]})
        programme = self.env['university.programme'].create({'name': 'Advanced Programme', 'code': 'P7-ADV', 'department_id': self.department.id, 'coordinator_id': self.users['coordinator'].id, 'required_credits': 3, 'duration_years': 1, 'policy_id': self.policy.id, 'course_ids': [(6,0,advanced.ids)]})
        student = self._new_student('prerequisite', programme)
        offering = self.env['university.course.offering'].create({'course_id': advanced.id, 'programme_id': programme.id, 'semester_id': self.semester.id, 'lecturer_id': self.users['lecturer'].id, 'policy_id': self.policy.id})
        offering.action_open()
        registration = self.env['university.course.registration'].create({'student_id': student.id, 'offering_id': offering.id})
        with self.assertRaises(ValidationError):
            registration.action_submit()
        offering.action_close()
        with self.assertRaises(ValidationError):
            registration.action_submit()

    def test_profile_document_controls_and_portal_mutations(self):
        applicant = self.env['student.university'].create({'name':'New Applicant','email':'p7-new-applicant@example.invalid','phone_number':'0700000000','university_id':self.uni.id})
        with self.assertRaises(ValidationError):
            applicant.with_user(self.users['registrar']).action_submit_application()
        doc=self.alice.document_ids[0]
        with self.assertRaises(UserError):
            doc.with_user(self.users['registrar']).write({'file_data':base64.b64encode(b'replacement')})
        website=self.env['website'].search([],limit=1)
        portal=import_module('odoo.addons.'+M+'.controllers.student_portal').AcademicStudentPortal()
        with MockRequest(self.env(user=self.alice.user_id),website=website,url_root='http://localhost:18079/'):
            portal.student_profile_save(phone_number='0799999999',registration_state='graduated',programme_id='999999')
            self.assertEqual(self.alice.phone_number,'0799999999')
            self.assertEqual(self.alice.registration_state,'registered')
            self.assertEqual(self.bob.phone_number,'0700000000')
            portal.student_course_register(offering_id=str(self.offering.id))
            self.assertEqual(len(self.alice.registration_ids),1)
