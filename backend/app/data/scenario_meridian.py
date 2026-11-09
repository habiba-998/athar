"""Scenario: "Meridian Synthetic Enterprise", a fictional mid-size company used as a safe digital twin.

EVERYTHING HERE IS INVENTED. No real organisation, person, host, account, credential or vulnerability is described or
tested, and nothing is scanned. The twin models the kinds of components found in a typical enterprise - an identity
provider (SSO), a directory, privileged and service accounts, application and infrastructure servers, databases, cloud
resources, network segments and the business services that depend on them - and the access relationships between them.

Provenance (source, collection date, confidence, validation) is DECLARED here to demonstrate the evidence model. The
"synthetic:*" sources are labels, not tools; the "synthetic_exercise" validation marks relationships that a fictional
authorised exercise is *pretended* to have confirmed. Nothing is validated in the real world.

Four assumed-breach starting points are provided as attack scenarios (assumptions, not findings). The default activates
two of them at once: a phished helpdesk analyst and an exploitable internet-facing portal.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import Asset, AttackScenario, Environment, Relationship, Service


def _a(id, name, name_ar, type, crit, segment, desc="", desc_ar="", exposure="internal", compromised=False, controls=()):  # noqa: A002
    return Asset(id=id, name=name, name_ar=name_ar, type=type, criticality=crit, exposure=exposure, compromised=compromised,
                 description=desc, description_ar=desc_ar, controls=list(controls), segment=segment)


def _r(id, s, t, type, priv, ev, src, at, use=None, use_ar=None, biz=False, svc=(), rec=None,  # noqa: A002
       why=None, why_ar=None, conf=None):
    y, m, d = (int(x) for x in at.split("-"))
    return Relationship(
        id=id, source=s, target=t, type=type, privilege=priv, evidence=ev, legitimate_use=use, legitimate_use_ar=use_ar,
        business_critical=biz, evidence_source=src, collected_at=datetime(y, m, d, tzinfo=timezone.utc), confidence=conf,
        validation="synthetic_exercise" if ev == "validated" else "none", rationale=why, rationale_ar=why_ar,
        supports_services=list(svc), recovery_hours=rec)


IAM = "synthetic:iam-export"
NET = "synthetic:network-flow-sample"
CFG = "synthetic:config-review"
EXE = "synthetic:authorised-exercise"
ASM = "synthetic:architecture-assumption"


def build_meridian_environment() -> Environment:
    assets = [
        # ---- identities
        _a("u-amal-help", "Amal (Helpdesk)", "أمل (مكتب المساعدة)", "user", 1, "corp", "Helpdesk analyst; credentials assumed phished.", "محللة مكتب مساعدة؛ يُفترض أن بيانات اعتمادها سُرقت بالتصيّد.", compromised=True),
        _a("u-yousef-dev", "Yousef (Developer)", "يوسف (مطوّر)", "user", 2, "corp"),
        _a("u-huda-fin", "Huda (Finance)", "هدى (المالية)", "user", 2, "corp"),
        _a("u-tariq-dba", "Tariq (DBA)", "طارق (مسؤول قواعد البيانات)", "user", 4, "corp", "Database administrator.", "مسؤول قواعد البيانات."),
        _a("u-nadia-secops", "Nadia (Security analyst)", "نادية (محللة أمن)", "user", 3, "mgmt"),
        _a("u-sami-admin", "Sami (Domain admin)", "سامي (مسؤول النطاق)", "user", 5, "mgmt", "Most privileged human identity.", "أعلى هوية بشرية صلاحيةً."),
        _a("u-lama-exec", "Lama (Executive)", "لمى (تنفيذية)", "user", 3, "corp"),
        _a("u-vendor", "Contractor account (ERP vendor)", "حساب مقاول (مورّد ERP)", "user", 1, "partner", "Third-party support account.", "حساب دعم تابع لطرف ثالث."),
        _a("grp-helpdesk", "Helpdesk group", "مجموعة مكتب المساعدة", "group", 2, "corp"),
        _a("grp-dev", "Developers group", "مجموعة المطوّرين", "group", 2, "corp"),
        _a("grp-finance", "Finance group", "مجموعة المالية", "group", 2, "corp"),
        _a("grp-dba", "Database administrators group", "مجموعة مسؤولي قواعد البيانات", "group", 3, "corp"),
        _a("grp-domain-admins", "Domain administrators group", "مجموعة مسؤولي النطاق", "group", 4, "mgmt"),
        _a("grp-vendors", "Vendors group", "مجموعة المورّدين", "group", 1, "partner"),
        _a("svc-web", "Web application service account", "حساب خدمة تطبيق الويب", "service_account", 3, "app"),
        _a("svc-ci", "CI/CD service account", "حساب خدمة التكامل المستمر", "service_account", 3, "mgmt"),
        _a("svc-backup", "Backup service account", "حساب خدمة النسخ الاحتياطي", "service_account", 3, "mgmt"),
        _a("svc-erp", "ERP service account", "حساب خدمة ERP", "service_account", 3, "app"),
        _a("svc-etl", "Analytics ETL service account", "حساب خدمة تحميل التحليلات", "service_account", 3, "app"),
        _a("idp-sso", "Corporate SSO (identity provider)", "تسجيل الدخول الموحّد (مزوّد الهوية)", "identity_provider", 5, "identity",
           "Federates sign-in for staff and applications.", "يوحّد تسجيل دخول الموظفين والتطبيقات.", exposure="internet", controls=["ctl-mfa"]),
        # ---- servers
        _a("web-portal", "Customer web portal", "بوابة العملاء", "server", 3, "dmz", "Internet-facing; assumed exploitable (assumption).", "متاحة عبر الإنترنت؛ يُفترض قابليتها للاستغلال (افتراض).", exposure="internet", compromised=True, controls=["ctl-waf", "ctl-fw-dmz"]),
        _a("api-gw", "API gateway", "بوابة الواجهات", "server", 3, "dmz", exposure="internet", controls=["ctl-fw-dmz"]),
        _a("app-orders", "Orders service", "خدمة الطلبات", "server", 4, "app", controls=["ctl-fw-core"]),
        _a("app-pay", "Payments service", "خدمة المدفوعات", "server", 4, "app", controls=["ctl-fw-core"]),
        _a("app-erp", "ERP application", "تطبيق ERP", "server", 4, "app", controls=["ctl-fw-core"]),
        _a("jump-host", "Admin jump host", "خادم القفز الإداري", "server", 4, "mgmt", controls=["ctl-edr", "ctl-pam"]),
        _a("ci-runner", "CI/CD runner", "منفّذ التكامل المستمر", "server", 4, "mgmt", controls=["ctl-edr"]),
        _a("dc-01", "Directory server", "خادم الدليل", "server", 5, "identity", "Holds credentials for all accounts.", "يحتفظ ببيانات اعتماد جميع الحسابات.", exposure="restricted", controls=["ctl-edr"]),
        _a("file-srv", "Finance file server", "خادم ملفات المالية", "server", 3, "corp"),
        _a("backup-srv", "Backup server", "خادم النسخ الاحتياطي", "server", 4, "mgmt"),
        _a("siem", "Security monitoring platform", "منصة المراقبة الأمنية", "server", 3, "mgmt"),
        # ---- data
        _a("db-orders", "Orders database", "قاعدة بيانات الطلبات", "database", 4, "data", exposure="restricted"),
        _a("db-customers", "Customer PII database", "قاعدة بيانات العملاء الشخصية", "database", 5, "data", "Customer personal data (synthetic).", "بيانات العملاء الشخصية (افتراضية).", exposure="restricted"),
        _a("db-payments", "Payments database", "قاعدة بيانات المدفوعات", "database", 5, "data", exposure="restricted"),
        _a("db-erp", "ERP / ledger database", "قاعدة بيانات ERP والدفتر", "database", 5, "data", exposure="restricted"),
        _a("db-hr", "Payroll and HR database", "قاعدة بيانات الرواتب والموارد البشرية", "database", 5, "data", exposure="restricted"),
        # ---- cloud
        _a("cloud-admin-role", "Cloud administrator role", "دور مسؤول السحابة", "cloud", 5, "cloud", exposure="restricted"),
        _a("s3-datalake", "Data lake bucket", "حاوية بحيرة البيانات", "cloud", 4, "cloud", exposure="restricted"),
        _a("s3-backups", "Offsite backup bucket", "حاوية النسخ الاحتياطي", "cloud", 4, "cloud", exposure="restricted"),
        _a("kms-vault", "Key management service", "خدمة إدارة المفاتيح", "cloud", 5, "cloud", exposure="restricted", controls=["ctl-mfa"]),
        # ---- controls (informational)
        _a("ctl-waf", "Web application firewall", "جدار حماية تطبيقات الويب", "control", 1, "dmz"),
        _a("ctl-fw-dmz", "DMZ firewall", "جدار حماية المنطقة العازلة", "control", 1, "dmz"),
        _a("ctl-fw-core", "Core network firewall", "جدار حماية الشبكة الأساسية", "control", 1, "app"),
        _a("ctl-edr", "Endpoint detection agent", "عميل رصد النقاط الطرفية", "control", 1, "mgmt"),
        _a("ctl-mfa", "MFA gateway", "بوابة المصادقة متعددة العوامل", "control", 1, "identity"),
        _a("ctl-pam", "Privileged access management", "إدارة الوصول المميّز", "control", 1, "mgmt"),
    ]
    R = _r
    rels = [
        # ---- membership
        R("m01", "u-amal-help", "grp-helpdesk", "member_of", "none", "observed", IAM, "2026-10-12", "Helpdesk role.", "دور مكتب المساعدة."),
        R("m02", "u-yousef-dev", "grp-dev", "member_of", "none", "observed", IAM, "2026-10-12"),
        R("m03", "u-huda-fin", "grp-finance", "member_of", "none", "observed", IAM, "2026-10-12"),
        R("m04", "u-tariq-dba", "grp-dba", "member_of", "none", "observed", IAM, "2026-10-12"),
        R("m05", "u-sami-admin", "grp-domain-admins", "member_of", "none", "observed", IAM, "2026-10-12"),
        R("m06", "u-vendor", "grp-vendors", "member_of", "none", "observed", IAM, "2026-10-12"),
        # ---- helpdesk and the identity provider
        R("a01", "grp-helpdesk", "jump-host", "can_login", "admin", "observed", IAM, "2026-02-03",
          why="Legacy bastion rule left from a past migration; no owner recorded.", why_ar="قاعدة قديمة متبقية من ترحيل سابق؛ بلا مالك مسجَّل."),
        R("i02", "grp-helpdesk", "idp-sso", "write_access", "write", "observed", IAM, "2026-10-14", "Password resets and MFA re-enrolment.", "إعادة تعيين كلمات المرور وتسجيل المصادقة.",
          svc=["svc-support"], rec=2, why="Helpdesk resets user passwords through the SSO admin console.", why_ar="يعيد مكتب المساعدة تعيين كلمات المرور عبر لوحة إدارة الدخول الموحّد."),
        R("i01", "idp-sso", "web-portal", "trusts", "none", "observed", CFG, "2026-10-01", "Staff and customers sign in through SSO.", "يسجّل الموظفون والعملاء الدخول عبر الدخول الموحّد.", True, ["svc-orders"], 1),
        R("i03", "idp-sso", "cloud-admin-role", "assumes_role", "admin", "observed", CFG, "2026-09-20", "Federated cloud console access.", "وصول موحّد إلى وحدة تحكم السحابة.", False, [], 4,
          why="Admins reach the cloud console by SSO federation.", why_ar="يصل المسؤولون إلى وحدة تحكم السحابة عبر الاتحاد."),
        R("i04", "idp-sso", "app-erp", "trusts", "none", "inferred", CFG, "2026-09-20", "ERP sign-in is delegated to SSO.", "تسجيل الدخول إلى ERP مفوَّض للدخول الموحّد.", True, ["svc-erp"], 2),
        # ---- vendor
        R("v01", "grp-vendors", "app-erp", "can_login", "write", "observed", IAM, "2026-08-30", "Vendor ERP support window.", "نافذة دعم مورّد ERP.", False, ["svc-erp"], 8,
          why="Third-party support for the ERP application.", why_ar="دعم طرف ثالث لتطبيق ERP."),
        # ---- jump host / admin plane
        R("a03", "jump-host", "dc-01", "network_access", "none", "inferred", CFG, "2026-09-15", "Admin RDP to the directory server.", "اتصال إداري بخادم الدليل.", True, ["svc-erp"], 6),
        R("a04", "jump-host", "app-erp", "admin_access", "admin", "observed", IAM, "2026-10-01", "Ops administer the ERP tier.", "تدير العمليات طبقة ERP.", False, ["svc-erp"], 4),
        R("a05", "jump-host", "backup-srv", "admin_access", "admin", "validated", EXE, "2026-09-05", "Ops administer backups.", "تدير العمليات النسخ الاحتياطي.", False, ["svc-backup"], 6,
          why="Confirmed in a fictional authorised exercise (synthetic).", why_ar="مؤكَّد في تمرين مصرَّح به افتراضي."),
        R("a06", "jump-host", "ci-runner", "network_access", "none", "inferred", CFG, "2026-09-15", "Build administration.", "إدارة منظومة البناء.", False, ["svc-devops"], 3),
        R("a07", "jump-host", "file-srv", "admin_access", "admin", "observed", IAM, "2026-10-01", "Ops administer the file server.", "تدير العمليات خادم الملفات."),
        R("a08", "jump-host", "svc-etl", "has_credentials", "none", "inferred", CFG, "2026-07-11", why="Credential kept in a job scheduler on the jump host.", why_ar="بيانات اعتماد محفوظة في مجدول مهام على خادم القفز."),
        R("a09", "jump-host", "app-orders", "admin_access", "admin", "observed", IAM, "2026-10-01", "Ops administer the orders tier.", "تدير العمليات طبقة الطلبات.", True, ["svc-orders"], 4),
        # ---- directory and domain admins
        R("d01", "dc-01", "idp-sso", "trusts", "none", "observed", CFG, "2026-10-01", "Directory synchronisation to SSO.", "مزامنة الدليل مع الدخول الموحّد.", True, ["svc-orders", "svc-erp"], 6),
        R("d02", "dc-01", "u-sami-admin", "has_credentials", "none", "inferred", CFG, "2026-09-15"),
        R("d03", "grp-domain-admins", "dc-01", "admin_access", "admin", "observed", IAM, "2026-10-12", "Domain administration.", "إدارة النطاق."),
        R("d04", "u-sami-admin", "cloud-admin-role", "assumes_role", "admin", "observed", IAM, "2026-10-12", "Cloud administration.", "إدارة السحابة."),
        R("d05", "u-sami-admin", "jump-host", "can_login", "admin", "observed", IAM, "2026-10-12", "Administrative sign-in.", "تسجيل دخول إداري."),
        # ---- web / application tier
        R("w01", "web-portal", "api-gw", "network_access", "none", "validated", EXE, "2026-09-05", "Portal calls the gateway.", "تستدعي البوابة بوابة الواجهات.", True, ["svc-orders"], 1),
        R("w02", "api-gw", "app-orders", "network_access", "none", "validated", EXE, "2026-09-05", "Gateway routes order calls.", "توجّه البوابة نداءات الطلبات.", True, ["svc-orders"], 1),
        R("w03", "api-gw", "app-pay", "network_access", "none", "observed", NET, "2026-10-20", "Gateway routes payment calls.", "توجّه البوابة نداءات الدفع.", True, ["svc-payments"], 1),
        R("w04", "app-orders", "db-orders", "write_access", "write", "observed", NET, "2026-10-20", "Order processing.", "معالجة الطلبات.", True, ["svc-orders"], 2),
        R("w05", "app-orders", "svc-web", "has_credentials", "none", "inferred", CFG, "2026-08-10", why="Connection string in an application config file.", why_ar="سلسلة اتصال في ملف إعدادات التطبيق."),
        R("w06", "svc-web", "db-customers", "read_access", "read", "validated", EXE, "2026-09-05", "Reads customer profiles for orders.", "يقرأ ملفات العملاء لمعالجة الطلبات.", True, ["svc-orders"], 2),
        R("w07", "app-pay", "db-payments", "write_access", "write", "observed", NET, "2026-10-20", "Payment records.", "سجلات المدفوعات.", True, ["svc-payments"], 3),
        R("w08", "app-pay", "kms-vault", "read_access", "read", "observed", NET, "2026-10-20", "Fetches payment keys.", "يجلب مفاتيح الدفع.", True, ["svc-payments"], 3),
        R("w09", "web-portal", "db-customers", "read_access", "read", "inferred", CFG, "2026-04-02",
          why="A direct database connection from the portal was seen in a config review; no business use recorded.", why_ar="رُصد اتصال مباشر بقاعدة البيانات من البوابة في مراجعة الإعدادات؛ بلا استخدام تجاري مسجَّل."),
        R("w10", "app-orders", "app-pay", "trusts", "none", "inferred", CFG, "2026-09-15", "Trusted internal payment call.", "نداء دفع داخلي موثوق.", False, ["svc-payments"], 2),
        # ---- ERP and finance
        R("e01", "u-huda-fin", "app-erp", "can_login", "write", "observed", IAM, "2026-10-12", "Finance close.", "الإقفال المالي.", False, ["svc-erp"], 2),
        R("e02", "grp-finance", "file-srv", "read_access", "read", "observed", IAM, "2026-10-12", "Shared finance reports.", "تقارير المالية المشتركة."),
        R("e03", "app-erp", "db-erp", "write_access", "write", "observed", NET, "2026-10-20", "ERP posts to the ledger.", "ينشر ERP في دفتر الأستاذ.", True, ["svc-erp"], 4),
        R("e04", "file-srv", "svc-erp", "has_credentials", "none", "inferred", CFG, "2026-03-01", why="Old export script holds a connection string.", why_ar="سكربت تصدير قديم يحمل سلسلة اتصال."),
        R("e05", "svc-erp", "db-erp", "write_access", "write", "validated", EXE, "2026-09-05", "Batch postings.", "ترحيلات دفعية.", True, ["svc-erp"], 4),
        R("e06", "app-erp", "db-hr", "read_access", "read", "observed", NET, "2026-10-20", "Payroll export.", "تصدير الرواتب.", False, ["svc-hr"], 6),
        R("e07", "u-lama-exec", "app-erp", "can_login", "read", "observed", IAM, "2026-10-12", "Board reporting.", "تقارير مجلس الإدارة."),
        # ---- database administration
        R("b01", "grp-dba", "db-erp", "admin_access", "admin", "observed", IAM, "2026-10-12", "Database administration.", "إدارة قواعد البيانات.", False, ["svc-erp"], 6),
        R("b02", "grp-dba", "db-customers", "admin_access", "admin", "observed", IAM, "2026-10-12", "Database administration.", "إدارة قواعد البيانات.", False, ["svc-orders"], 6),
        R("b03", "grp-dba", "db-payments", "admin_access", "admin", "observed", IAM, "2026-10-12", "Database administration.", "إدارة قواعد البيانات.", False, ["svc-payments"], 6),
        R("b04", "grp-dba", "db-hr", "admin_access", "admin", "observed", IAM, "2026-10-12", "Database administration.", "إدارة قواعد البيانات.", False, ["svc-hr"], 6),
        R("b05", "u-tariq-dba", "jump-host", "can_login", "write", "observed", IAM, "2026-10-12", "DBA maintenance sessions.", "جلسات صيانة قواعد البيانات."),
        # ---- delivery pipeline
        R("c01", "grp-dev", "ci-runner", "can_login", "write", "observed", IAM, "2026-10-12", "Developers trigger builds.", "يشغّل المطوّرون عمليات البناء.", False, ["svc-devops"], 3),
        R("c02", "ci-runner", "svc-ci", "has_credentials", "none", "validated", EXE, "2026-09-05", why="A deploy token sits on the runner (fictional exercise finding).", why_ar="رمز نشر موجود على المنفّذ (نتيجة تمرين افتراضي)."),
        R("c03", "svc-ci", "app-orders", "admin_access", "admin", "observed", IAM, "2026-10-01", "Deploys the orders service.", "ينشر خدمة الطلبات.", False, ["svc-devops"], 3),
        R("c04", "svc-ci", "app-pay", "admin_access", "admin", "observed", IAM, "2026-10-01", why="Same deploy role reused for payments; broader than needed.", why_ar="دور النشر نفسه مستخدم للمدفوعات؛ أوسع من اللازم."),
        R("c05", "svc-ci", "kms-vault", "read_access", "read", "inferred", CFG, "2026-07-11", "Reads deployment secrets.", "يقرأ أسرار النشر.", False, ["svc-devops"], 3),
        R("c06", "svc-ci", "cloud-admin-role", "assumes_role", "admin", "theoretical", ASM, "2026-05-02", why="Role trust policy looks broader than intended; not confirmed.", why_ar="تبدو سياسة الثقة بالدور أوسع من المقصود؛ غير مؤكَّد."),
        # ---- backup
        R("k01", "backup-srv", "svc-backup", "has_credentials", "none", "inferred", CFG, "2026-09-15"),
        R("k02", "svc-backup", "s3-backups", "write_access", "write", "observed", IAM, "2026-10-12", "Offsite backups.", "نسخ احتياطي خارجي.", True, ["svc-backup"], 6),
        R("k03", "svc-backup", "db-erp", "read_access", "read", "observed", IAM, "2026-10-12", "Nightly backup.", "نسخ ليلي.", True, ["svc-backup"], 6),
        R("k04", "svc-backup", "db-customers", "read_access", "read", "observed", IAM, "2026-10-12", "Nightly backup.", "نسخ ليلي.", True, ["svc-backup"], 6),
        R("k05", "svc-backup", "db-payments", "read_access", "read", "observed", IAM, "2026-10-12", "Nightly backup.", "نسخ ليلي.", True, ["svc-backup"], 6),
        R("k06", "svc-backup", "db-hr", "read_access", "read", "observed", IAM, "2026-10-12", "Nightly backup.", "نسخ ليلي.", True, ["svc-backup"], 6),
        R("k07", "backup-srv", "s3-backups", "write_access", "write", "validated", EXE, "2026-09-05", "Backup jobs.", "مهام النسخ الاحتياطي.", True, ["svc-backup"], 6),
        # ---- analytics
        R("t01", "svc-etl", "s3-datalake", "write_access", "write", "observed", IAM, "2026-10-12", "ETL loads the data lake.", "تحميل بحيرة البيانات."),
        R("t02", "svc-etl", "db-customers", "read_access", "read", "inferred", CFG, "2026-07-11", "Analytics extract.", "استخراج التحليلات."),
        # ---- cloud administration
        R("l01", "cloud-admin-role", "s3-datalake", "admin_access", "admin", "observed", CFG, "2026-09-20"),
        R("l02", "cloud-admin-role", "s3-backups", "admin_access", "admin", "observed", CFG, "2026-09-20"),
        R("l03", "cloud-admin-role", "kms-vault", "admin_access", "admin", "observed", CFG, "2026-09-20"),
        # ---- security operations
        R("s01", "u-nadia-secops", "siem", "can_login", "admin", "observed", IAM, "2026-10-12", "Security monitoring.", "المراقبة الأمنية."),
        R("s02", "siem", "jump-host", "network_access", "none", "theoretical", ASM, "2026-05-02", why="A SIEM forwarder might allow remote execution; unverified.", why_ar="قد يتيح وكيل إعادة التوجيه تنفيذًا عن بُعد؛ غير متحقَّق منه."),
    ]
    services = [
        Service(id="svc-orders", name="Online ordering", name_ar="الطلبات عبر الإنترنت", criticality=5, rto_hours=4, description="Customers place and track orders.", description_ar="يقدّم العملاء الطلبات ويتابعونها."),
        Service(id="svc-payments", name="Payment processing", name_ar="معالجة المدفوعات", criticality=5, rto_hours=2, description="Card and bank payments.", description_ar="مدفوعات البطاقات والبنوك."),
        Service(id="svc-erp", name="ERP and finance close", name_ar="ERP والإقفال المالي", criticality=4, rto_hours=24),
        Service(id="svc-hr", name="Payroll and HR", name_ar="الرواتب والموارد البشرية", criticality=4, rto_hours=48),
        Service(id="svc-backup", name="Backup and recovery", name_ar="النسخ الاحتياطي والاسترجاع", criticality=4, rto_hours=24),
        Service(id="svc-devops", name="Software delivery", name_ar="تسليم البرمجيات", criticality=3, rto_hours=72),
        Service(id="svc-support", name="Customer support desk", name_ar="مكتب دعم العملاء", criticality=3, rto_hours=8),
    ]
    scenarios = [
        AttackScenario(id="sc-phish-helpdesk", name="Phished helpdesk analyst", name_ar="تصيّد محللة مكتب المساعدة",
                       compromised=["u-amal-help", "web-portal"],
                       description="Default: a helpdesk account is phished and the internet-facing portal is assumed exploitable.",
                       description_ar="الافتراضي: تصيّد حساب مكتب المساعدة وافتراض قابلية استغلال بوابة الإنترنت."),
        AttackScenario(id="sc-vendor", name="Compromised vendor account", name_ar="حساب مورّد مخترَق", compromised=["u-vendor"],
                       description="A third-party support account is taken over.", description_ar="الاستيلاء على حساب دعم تابع لطرف ثالث."),
        AttackScenario(id="sc-portal-only", name="Internet-facing portal exploited", name_ar="استغلال بوابة الإنترنت", compromised=["web-portal"],
                       description="Only the portal is assumed compromised.", description_ar="يُفترض اختراق البوابة فقط."),
        AttackScenario(id="sc-insider-dev", name="Developer account misuse", name_ar="إساءة استخدام حساب مطوّر", compromised=["u-yousef-dev"],
                       description="A developer account is misused (insider or stolen).", description_ar="إساءة استخدام حساب مطوّر (داخلي أو مسروق)."),
    ]
    return Environment(name="Meridian Synthetic Enterprise (digital twin)", name_ar="شركة ميريديان الافتراضية (توأم رقمي)",
                       assets=assets, relationships=rels, services=services, attack_scenarios=scenarios)
