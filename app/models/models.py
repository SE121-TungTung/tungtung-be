from typing import Optional
import datetime
import decimal
import uuid

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Double, ForeignKeyConstraint, Integer, Numeric, PrimaryKeyConstraint, String, Table, Text, Time, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB, OID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass


t_pg_stat_statements = Table(
    'pg_stat_statements', Base.metadata,
    Column('userid', OID),
    Column('dbid', OID),
    Column('toplevel', Boolean),
    Column('queryid', BigInteger),
    Column('query', Text),
    Column('plans', BigInteger),
    Column('total_plan_time', Double(53)),
    Column('min_plan_time', Double(53)),
    Column('max_plan_time', Double(53)),
    Column('mean_plan_time', Double(53)),
    Column('stddev_plan_time', Double(53)),
    Column('calls', BigInteger),
    Column('total_exec_time', Double(53)),
    Column('min_exec_time', Double(53)),
    Column('max_exec_time', Double(53)),
    Column('mean_exec_time', Double(53)),
    Column('stddev_exec_time', Double(53)),
    Column('rows', BigInteger),
    Column('shared_blks_hit', BigInteger),
    Column('shared_blks_read', BigInteger),
    Column('shared_blks_dirtied', BigInteger),
    Column('shared_blks_written', BigInteger),
    Column('local_blks_hit', BigInteger),
    Column('local_blks_read', BigInteger),
    Column('local_blks_dirtied', BigInteger),
    Column('local_blks_written', BigInteger),
    Column('temp_blks_read', BigInteger),
    Column('temp_blks_written', BigInteger),
    Column('shared_blk_read_time', Double(53)),
    Column('shared_blk_write_time', Double(53)),
    Column('local_blk_read_time', Double(53)),
    Column('local_blk_write_time', Double(53)),
    Column('temp_blk_read_time', Double(53)),
    Column('temp_blk_write_time', Double(53)),
    Column('wal_records', BigInteger),
    Column('wal_fpi', BigInteger),
    Column('wal_bytes', Numeric),
    Column('jit_functions', BigInteger),
    Column('jit_generation_time', Double(53)),
    Column('jit_inlining_count', BigInteger),
    Column('jit_inlining_time', Double(53)),
    Column('jit_optimization_count', BigInteger),
    Column('jit_optimization_time', Double(53)),
    Column('jit_emission_count', BigInteger),
    Column('jit_emission_time', Double(53)),
    Column('jit_deform_count', BigInteger),
    Column('jit_deform_time', Double(53)),
    Column('stats_since', DateTime(True)),
    Column('minmax_stats_since', DateTime(True))
)


t_pg_stat_statements_info = Table(
    'pg_stat_statements_info', Base.metadata,
    Column('dealloc', BigInteger),
    Column('stats_reset', DateTime(True))
)


class Roles(Base):
    __tablename__ = 'roles'
    __table_args__ = (
        PrimaryKeyConstraint('role_id', name='roles_pkey'),
        UniqueConstraint('role_code', name='roles_role_code_key'),
        UniqueConstraint('role_name', name='roles_role_name_key')
    )

    role_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role_code: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    users: Mapped[list['Users']] = relationship('Users', back_populates='role')


class Rooms(Base):
    __tablename__ = 'rooms'
    __table_args__ = (
        PrimaryKeyConstraint('room_id', name='rooms_pkey'),
        UniqueConstraint('room_name', name='rooms_room_name_key')
    )

    room_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    room_name: Mapped[str] = mapped_column(String(50), nullable=False)
    capacity: Mapped[Optional[int]] = mapped_column(Integer)
    equipment: Mapped[Optional[dict]] = mapped_column(JSONB)

    classes: Mapped[list['Classes']] = relationship('Classes', back_populates='room')
    schedules: Mapped[list['Schedules']] = relationship('Schedules', back_populates='room')


class Subjects(Base):
    __tablename__ = 'subjects'
    __table_args__ = (
        PrimaryKeyConstraint('subject_id', name='subjects_pkey'),
        UniqueConstraint('subject_code', name='subjects_subject_code_key')
    )

    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    subject_name: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_code: Mapped[Optional[str]] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)

    exams: Mapped[list['Exams']] = relationship('Exams', back_populates='subject')
    classes: Mapped[list['Classes']] = relationship('Classes', back_populates='subject')


class Users(Base):
    __tablename__ = 'users'
    __table_args__ = (
        ForeignKeyConstraint(['role_id'], ['roles.role_id'], name='users_role_id_fkey'),
        PrimaryKeyConstraint('user_id', name='users_pkey'),
        UniqueConstraint('email', name='users_email_key'),
        UniqueConstraint('username', name='users_username_key')
    )

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    username: Mapped[str] = mapped_column(String(50), nullable=False)
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(20))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    role_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    role: Mapped[Optional['Roles']] = relationship('Roles', back_populates='users')
    exams: Mapped[list['Exams']] = relationship('Exams', back_populates='users')
    notifications: Mapped[list['Notifications']] = relationship('Notifications', back_populates='sender')
    students: Mapped['Students'] = relationship('Students', uselist=False, back_populates='user')
    teachers: Mapped['Teachers'] = relationship('Teachers', uselist=False, back_populates='user')
    notification_reads: Mapped[list['NotificationReads']] = relationship('NotificationReads', back_populates='user')
    messages: Mapped[list['Messages']] = relationship('Messages', foreign_keys='[Messages.recipient_id]', back_populates='recipient')
    messages_: Mapped[list['Messages']] = relationship('Messages', foreign_keys='[Messages.sender_id]', back_populates='sender')


class Exams(Base):
    __tablename__ = 'exams'
    __table_args__ = (
        ForeignKeyConstraint(['created_by'], ['users.user_id'], name='exams_created_by_fkey'),
        ForeignKeyConstraint(['subject_id'], ['subjects.subject_id'], name='exams_subject_id_fkey'),
        PrimaryKeyConstraint('exam_id', name='exams_pkey')
    )

    exam_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    exam_title: Mapped[str] = mapped_column(String(200), nullable=False)
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    exam_type: Mapped[Optional[str]] = mapped_column(String(50))
    level: Mapped[Optional[str]] = mapped_column(String(20))
    time_limit_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    total_questions: Mapped[Optional[int]] = mapped_column(Integer)
    passing_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    users: Mapped[Optional['Users']] = relationship('Users', back_populates='exams')
    subject: Mapped[Optional['Subjects']] = relationship('Subjects', back_populates='exams')
    exam_results: Mapped[list['ExamResults']] = relationship('ExamResults', back_populates='exam')
    questions: Mapped[list['Questions']] = relationship('Questions', back_populates='exam')


class Notifications(Base):
    __tablename__ = 'notifications'
    __table_args__ = (
        ForeignKeyConstraint(['sender_id'], ['users.user_id'], name='notifications_sender_id_fkey'),
        PrimaryKeyConstraint('notification_id', name='notifications_pkey')
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    sender_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    target_type: Mapped[Optional[str]] = mapped_column(String(20))
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    is_active: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    sender: Mapped[Optional['Users']] = relationship('Users', back_populates='notifications')
    notification_reads: Mapped[list['NotificationReads']] = relationship('NotificationReads', back_populates='notification')


class Students(Base):
    __tablename__ = 'students'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='students_user_id_fkey'),
        PrimaryKeyConstraint('student_id', name='students_pkey'),
        UniqueConstraint('student_code', name='students_student_code_key'),
        UniqueConstraint('user_id', name='students_user_id_key')
    )

    student_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    student_code: Mapped[Optional[str]] = mapped_column(String(20))
    current_level: Mapped[Optional[str]] = mapped_column(String(20))
    target_level: Mapped[Optional[str]] = mapped_column(String(20))
    parent_phone: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Active'::character varying"))

    user: Mapped['Users'] = relationship('Users', back_populates='students')
    exam_results: Mapped[list['ExamResults']] = relationship('ExamResults', back_populates='student')
    class_enrollments: Mapped[list['ClassEnrollments']] = relationship('ClassEnrollments', back_populates='student')
    attendances: Mapped[list['Attendances']] = relationship('Attendances', back_populates='student')


class Teachers(Base):
    __tablename__ = 'teachers'
    __table_args__ = (
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='teachers_user_id_fkey'),
        PrimaryKeyConstraint('teacher_id', name='teachers_pkey'),
        UniqueConstraint('employee_code', name='teachers_employee_code_key'),
        UniqueConstraint('user_id', name='teachers_user_id_key')
    )

    teacher_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    employee_code: Mapped[Optional[str]] = mapped_column(String(20))
    teacher_type: Mapped[Optional[str]] = mapped_column(String(50))
    specialization: Mapped[Optional[str]] = mapped_column(Text)
    hourly_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(10, 2))
    current_kpi_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Active'::character varying"))

    user: Mapped['Users'] = relationship('Users', back_populates='teachers')
    classes: Mapped[list['Classes']] = relationship('Classes', back_populates='teacher')
    teacher_kpi_monthly: Mapped[list['TeacherKpiMonthly']] = relationship('TeacherKpiMonthly', back_populates='teacher')
    teacher_payroll: Mapped[list['TeacherPayroll']] = relationship('TeacherPayroll', back_populates='teacher')


class Classes(Base):
    __tablename__ = 'classes'
    __table_args__ = (
        ForeignKeyConstraint(['room_id'], ['rooms.room_id'], name='classes_room_id_fkey'),
        ForeignKeyConstraint(['subject_id'], ['subjects.subject_id'], name='classes_subject_id_fkey'),
        ForeignKeyConstraint(['teacher_id'], ['teachers.teacher_id'], name='classes_teacher_id_fkey'),
        PrimaryKeyConstraint('class_id', name='classes_pkey'),
        UniqueConstraint('class_code', name='classes_class_code_key')
    )

    class_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    class_name: Mapped[str] = mapped_column(String(100), nullable=False)
    class_code: Mapped[Optional[str]] = mapped_column(String(20))
    subject_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    teacher_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    room_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    start_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    end_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    schedule_pattern: Mapped[Optional[dict]] = mapped_column(JSONB)
    max_students: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('15'))
    current_students: Mapped[Optional[int]] = mapped_column(Integer, server_default=text('0'))
    tuition_fee: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(15, 2))
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Active'::character varying"))

    room: Mapped[Optional['Rooms']] = relationship('Rooms', back_populates='classes')
    subject: Mapped[Optional['Subjects']] = relationship('Subjects', back_populates='classes')
    teacher: Mapped[Optional['Teachers']] = relationship('Teachers', back_populates='classes')
    class_enrollments: Mapped[list['ClassEnrollments']] = relationship('ClassEnrollments', back_populates='class_')
    messages: Mapped[list['Messages']] = relationship('Messages', back_populates='class_')
    schedules: Mapped[list['Schedules']] = relationship('Schedules', back_populates='class_')


class ExamResults(Base):
    __tablename__ = 'exam_results'
    __table_args__ = (
        ForeignKeyConstraint(['exam_id'], ['exams.exam_id'], name='exam_results_exam_id_fkey'),
        ForeignKeyConstraint(['student_id'], ['students.student_id'], name='exam_results_student_id_fkey'),
        PrimaryKeyConstraint('result_id', name='exam_results_pkey')
    )

    result_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    exam_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    student_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    start_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    end_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime)
    score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    percentage: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    band_score: Mapped[Optional[str]] = mapped_column(String(10))
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Completed'::character varying"))
    ai_feedback: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    exam: Mapped[Optional['Exams']] = relationship('Exams', back_populates='exam_results')
    student: Mapped[Optional['Students']] = relationship('Students', back_populates='exam_results')
    student_answers: Mapped[list['StudentAnswers']] = relationship('StudentAnswers', back_populates='result')


class NotificationReads(Base):
    __tablename__ = 'notification_reads'
    __table_args__ = (
        ForeignKeyConstraint(['notification_id'], ['notifications.notification_id'], ondelete='CASCADE', name='notification_reads_notification_id_fkey'),
        ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE', name='notification_reads_user_id_fkey'),
        PrimaryKeyConstraint('notification_id', 'user_id', name='notification_reads_pkey')
    )

    notification_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    read_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    notification: Mapped['Notifications'] = relationship('Notifications', back_populates='notification_reads')
    user: Mapped['Users'] = relationship('Users', back_populates='notification_reads')


class Questions(Base):
    __tablename__ = 'questions'
    __table_args__ = (
        ForeignKeyConstraint(['exam_id'], ['exams.exam_id'], ondelete='CASCADE', name='questions_exam_id_fkey'),
        PrimaryKeyConstraint('question_id', name='questions_pkey')
    )

    question_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    exam_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    question_type: Mapped[Optional[str]] = mapped_column(String(50))
    options: Mapped[Optional[dict]] = mapped_column(JSONB)
    correct_answer: Mapped[Optional[str]] = mapped_column(Text)
    points: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2), server_default=text('1.00'))
    audio_url: Mapped[Optional[str]] = mapped_column(String(500))

    exam: Mapped[Optional['Exams']] = relationship('Exams', back_populates='questions')
    student_answers: Mapped[list['StudentAnswers']] = relationship('StudentAnswers', back_populates='question')


class TeacherKpiMonthly(Base):
    __tablename__ = 'teacher_kpi_monthly'
    __table_args__ = (
        ForeignKeyConstraint(['teacher_id'], ['teachers.teacher_id'], name='teacher_kpi_monthly_teacher_id_fkey'),
        PrimaryKeyConstraint('kpi_id', name='teacher_kpi_monthly_pkey'),
        UniqueConstraint('teacher_id', 'evaluation_month', name='teacher_kpi_monthly_teacher_id_evaluation_month_key')
    )

    kpi_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    teacher_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    evaluation_month: Mapped[Optional[datetime.date]] = mapped_column(Date)
    classes_taught: Mapped[Optional[int]] = mapped_column(Integer)
    teaching_hours: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 2))
    attendance_rate: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    student_satisfaction: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(3, 2))
    overall_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    bonus_amount: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(15, 2))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    teacher: Mapped[Optional['Teachers']] = relationship('Teachers', back_populates='teacher_kpi_monthly')


class TeacherPayroll(Base):
    __tablename__ = 'teacher_payroll'
    __table_args__ = (
        ForeignKeyConstraint(['teacher_id'], ['teachers.teacher_id'], name='teacher_payroll_teacher_id_fkey'),
        PrimaryKeyConstraint('payroll_id', name='teacher_payroll_pkey')
    )

    payroll_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    teacher_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    pay_period_start: Mapped[Optional[datetime.date]] = mapped_column(Date)
    pay_period_end: Mapped[Optional[datetime.date]] = mapped_column(Date)
    total_hours: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(8, 2))
    base_pay: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(15, 2))
    kpi_bonus: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(15, 2))
    total_pay: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(15, 2))
    payment_status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Calculated'::character varying"))
    payment_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    teacher: Mapped[Optional['Teachers']] = relationship('Teachers', back_populates='teacher_payroll')


class ClassEnrollments(Base):
    __tablename__ = 'class_enrollments'
    __table_args__ = (
        ForeignKeyConstraint(['class_id'], ['classes.class_id'], name='class_enrollments_class_id_fkey'),
        ForeignKeyConstraint(['student_id'], ['students.student_id'], name='class_enrollments_student_id_fkey'),
        PrimaryKeyConstraint('enrollment_id', name='class_enrollments_pkey'),
        UniqueConstraint('student_id', 'class_id', name='class_enrollments_student_id_class_id_key')
    )

    enrollment_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    student_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    class_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    enrollment_date: Mapped[Optional[datetime.date]] = mapped_column(Date, server_default=text('CURRENT_DATE'))
    payment_status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Pending'::character varying"))
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Enrolled'::character varying"))

    class_: Mapped[Optional['Classes']] = relationship('Classes', back_populates='class_enrollments')
    student: Mapped[Optional['Students']] = relationship('Students', back_populates='class_enrollments')


class Messages(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        ForeignKeyConstraint(['class_id'], ['classes.class_id'], name='messages_class_id_fkey'),
        ForeignKeyConstraint(['recipient_id'], ['users.user_id'], name='messages_recipient_id_fkey'),
        ForeignKeyConstraint(['sender_id'], ['users.user_id'], name='messages_sender_id_fkey'),
        PrimaryKeyConstraint('message_id', name='messages_pkey')
    )

    message_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    sender_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    recipient_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    class_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    content: Mapped[Optional[str]] = mapped_column(Text)
    message_type: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'text'::character varying"))
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_read: Mapped[Optional[bool]] = mapped_column(Boolean, server_default=text('false'))
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    class_: Mapped[Optional['Classes']] = relationship('Classes', back_populates='messages')
    recipient: Mapped[Optional['Users']] = relationship('Users', foreign_keys=[recipient_id], back_populates='messages')
    sender: Mapped[Optional['Users']] = relationship('Users', foreign_keys=[sender_id], back_populates='messages_')


class Schedules(Base):
    __tablename__ = 'schedules'
    __table_args__ = (
        ForeignKeyConstraint(['class_id'], ['classes.class_id'], name='schedules_class_id_fkey'),
        ForeignKeyConstraint(['room_id'], ['rooms.room_id'], name='schedules_room_id_fkey'),
        PrimaryKeyConstraint('schedule_id', name='schedules_pkey')
    )

    schedule_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    class_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    lesson_title: Mapped[Optional[str]] = mapped_column(String(200))
    schedule_date: Mapped[Optional[datetime.date]] = mapped_column(Date)
    start_time: Mapped[Optional[datetime.time]] = mapped_column(Time)
    end_time: Mapped[Optional[datetime.time]] = mapped_column(Time)
    room_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    lesson_content: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Scheduled'::character varying"))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))

    class_: Mapped[Optional['Classes']] = relationship('Classes', back_populates='schedules')
    room: Mapped[Optional['Rooms']] = relationship('Rooms', back_populates='schedules')
    attendances: Mapped[list['Attendances']] = relationship('Attendances', back_populates='schedule')


class StudentAnswers(Base):
    __tablename__ = 'student_answers'
    __table_args__ = (
        ForeignKeyConstraint(['question_id'], ['questions.question_id'], name='student_answers_question_id_fkey'),
        ForeignKeyConstraint(['result_id'], ['exam_results.result_id'], ondelete='CASCADE', name='student_answers_result_id_fkey'),
        PrimaryKeyConstraint('answer_id', name='student_answers_pkey')
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    result_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    question_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    student_answer: Mapped[Optional[str]] = mapped_column(Text)
    audio_answer_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean)
    points_earned: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    ai_score: Mapped[Optional[decimal.Decimal]] = mapped_column(Numeric(5, 2))
    ai_feedback: Mapped[Optional[str]] = mapped_column(Text)

    question: Mapped[Optional['Questions']] = relationship('Questions', back_populates='student_answers')
    result: Mapped[Optional['ExamResults']] = relationship('ExamResults', back_populates='student_answers')


class Attendances(Base):
    __tablename__ = 'attendances'
    __table_args__ = (
        ForeignKeyConstraint(['schedule_id'], ['schedules.schedule_id'], name='attendances_schedule_id_fkey'),
        ForeignKeyConstraint(['student_id'], ['students.student_id'], name='attendances_student_id_fkey'),
        PrimaryKeyConstraint('attendance_id', name='attendances_pkey'),
        UniqueConstraint('schedule_id', 'student_id', name='attendances_schedule_id_student_id_key')
    )

    attendance_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=text('uuid_generate_v4()'))
    schedule_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    student_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid)
    status: Mapped[Optional[str]] = mapped_column(String(20), server_default=text("'Present'::character varying"))
    check_in_time: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime, server_default=text('CURRENT_TIMESTAMP'))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    schedule: Mapped[Optional['Schedules']] = relationship('Schedules', back_populates='attendances')
    student: Mapped[Optional['Students']] = relationship('Students', back_populates='attendances')
