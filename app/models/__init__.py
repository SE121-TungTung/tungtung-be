from .academic import  Room, Course, ClassEnrollment, Class
from .user import User
from .session_attendance import AttendanceRecord, ClassSession
# from .assessment import QuestionBank, Test, TestQuestion, TestAttempt, TestResponse
from .file_upload import FileUpload
from .message import Message, MessageRecipient, ChatRoom, ChatRoomMember
from .exam_structure import ExamType, ExamStructure, ExamStructureSection, ExamStructurePart
from .test import Test, TestSection, TestSectionPart, QuestionBank, TestQuestion, TestAttempt, TestResponse, QuestionGroup
from .notification import Notification
from .kpi import (
    # New Lotus KPI models
    KPITemplate, KPITemplateMetric, KPIPeriod, KPIRecord,
    KPIMetricResult, KPIApprovalLog, SupportCalcEntry,
    # Deprecated (kept for backward compat)
    KpiTier, KpiCriteria, TeacherPayrollConfig,
    TeacherMonthlyKpi, KpiCalculationJob, PayrollRun,
    KpiRawMetric, KpiDispute, Salary, SalaryAdjustment
)
from .finance import Invoice, Payment, Refund, ReportExportJob
from .ga_schedule import GARun, GAScheduleProposal, TeacherUnavailability