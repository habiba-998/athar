"""Scenario: "Harbor Synthetic Logistics", a fictional mid-size company.

EVERYTHING HERE IS INVENTED. No real organisation, person, host, credential or vulnerability is described or tested.
The scenario encodes a set of access relationships that are *typical* of real environments (stale bastion access,
credentials left on a CI runner, an application service account that can read customer data, an over-privileged deploy
role) so the engine has something realistic to reason about. ATHAR does not exploit anything: it only walks this graph.

Two assumed-breach starting points (assumptions, not findings):
  * u-lina  - a helpdesk analyst whose credentials were phished
  * web-ext - the internet-facing customer portal, assumed exploitable through an application flaw
"""
from __future__ import annotations

from ..models import Asset, Environment, Relationship


def _a(id, name, name_ar, type, crit, desc, desc_ar, exposure="internal", compromised=False, controls=()):  # noqa: A002
    return Asset(id=id, name=name, name_ar=name_ar, type=type, criticality=crit, exposure=exposure, compromised=compromised,
                 description=desc, description_ar=desc_ar, controls=list(controls))


def _r(id, s, t, type, privilege, evidence, use=None, use_ar=None, biz=False):  # noqa: A002
    return Relationship(id=id, source=s, target=t, type=type, privilege=privilege, evidence=evidence,
                        legitimate_use=use, legitimate_use_ar=use_ar, business_critical=biz)


def build_harbor_environment() -> Environment:
    assets = [
        # ---- identities (different privilege levels)
        _a("u-lina", "Lina (Helpdesk)", "لينا (مكتب المساعدة)", "user", 1, "Helpdesk analyst; credentials assumed phished.", "محللة مكتب مساعدة؛ يُفترض أن بيانات اعتمادها سُرقت بالتصيّد.", compromised=True),
        _a("u-omar-hr", "Omar (HR)", "عمر (الموارد البشرية)", "user", 2, "HR analyst processing payroll.", "محلل موارد بشرية يعالج الرواتب."),
        _a("u-sara-dev", "Sara (Developer)", "سارة (مطوّرة)", "user", 2, "Application developer.", "مطوّرة تطبيقات."),
        _a("u-fahad-fin", "Fahad (Finance)", "فهد (المالية)", "user", 2, "Finance analyst.", "محلل مالي."),
        _a("u-noura-dba", "Noura (DBA)", "نورة (مسؤولة قواعد البيانات)", "user", 4, "Database administrator (privileged).", "مسؤولة قواعد البيانات (صلاحيات مرتفعة)."),
        _a("u-khalid-it", "Khalid (IT admin)", "خالد (مسؤول التقنية)", "user", 5, "Domain and cloud administrator (most privileged identity).", "مسؤول النطاق والسحابة (أعلى هوية صلاحيةً)."),
        _a("u-reem-exec", "Reem (Executive)", "ريم (تنفيذية)", "user", 3, "Executive with board-reporting access.", "تنفيذية لديها وصول لتقارير مجلس الإدارة."),
        _a("svc-app", "Orders app service account", "حساب خدمة تطبيق الطلبات", "service_account", 3, "Runs the orders application.", "يشغّل تطبيق الطلبات."),
        _a("svc-ci", "CI/CD service account", "حساب خدمة التكامل المستمر", "service_account", 3, "Deploys builds.", "ينشر الإصدارات."),
        _a("svc-backup", "Backup service account", "حساب خدمة النسخ الاحتياطي", "service_account", 3, "Nightly backups.", "نسخ احتياطي ليلي."),
        _a("grp-helpdesk", "Helpdesk group", "مجموعة مكتب المساعدة", "group", 2, "Helpdesk staff.", "موظفو مكتب المساعدة."),
        _a("grp-developers", "Developers group", "مجموعة المطوّرين", "group", 2, "Application developers.", "مطوّرو التطبيقات."),
        _a("grp-finance", "Finance group", "مجموعة المالية", "group", 2, "Finance staff.", "موظفو المالية."),
        _a("grp-it-admins", "IT administrators group", "مجموعة مسؤولي التقنية", "group", 4, "Infrastructure administrators.", "مسؤولو البنية التحتية."),
        # ---- servers
        _a("web-ext", "Customer web portal", "بوابة العملاء", "server", 3, "Internet-facing portal; assumed exploitable (assumption).", "بوابة متاحة عبر الإنترنت؛ يُفترض قابليتها للاستغلال (افتراض).", exposure="internet", compromised=True, controls=["ctl-waf", "ctl-fw"]),
        _a("api-orders", "Orders API server", "خادم واجهة الطلبات", "server", 4, "Business logic for orders.", "منطق الأعمال للطلبات.", controls=["ctl-fw"]),
        _a("app-batch", "Batch processing server", "خادم المعالجة الدفعية", "server", 3, "Nightly ETL jobs.", "مهام ETL الليلية."),
        _a("jump-host", "Admin jump host", "خادم القفز الإداري", "server", 4, "Administrative bastion.", "خادم إداري وسيط.", controls=["ctl-edr", "ctl-mfa"]),
        _a("ci-runner", "CI/CD runner", "منفّذ التكامل المستمر", "server", 4, "Builds and deploys.", "يبني وينشر.", controls=["ctl-edr"]),
        _a("file-srv", "Finance file server", "خادم ملفات المالية", "server", 3, "Shared finance reports.", "تقارير المالية المشتركة."),
        _a("backup-srv", "Backup server", "خادم النسخ الاحتياطي", "server", 4, "Runs backup jobs.", "يشغّل مهام النسخ الاحتياطي."),
        _a("dc-01", "Directory server", "خادم الدليل", "server", 5, "Identity directory; holds credentials for all accounts.", "دليل الهويات؛ يحتفظ ببيانات اعتماد جميع الحسابات.", exposure="restricted"),
        # ---- data
        _a("db-orders", "Orders database", "قاعدة بيانات الطلبات", "database", 4, "Order records.", "سجلات الطلبات.", exposure="restricted"),
        _a("db-customers", "Customer PII database", "قاعدة بيانات العملاء الشخصية", "database", 5, "Customer personal data (synthetic).", "بيانات العملاء الشخصية (افتراضية).", exposure="restricted"),
        _a("db-payroll", "Payroll database", "قاعدة بيانات الرواتب", "database", 5, "Payroll records (synthetic).", "سجلات الرواتب (افتراضية).", exposure="restricted"),
        _a("db-ledger", "Finance ledger database", "قاعدة بيانات دفتر الأستاذ", "database", 5, "General ledger (synthetic).", "دفتر الأستاذ العام (افتراضي).", exposure="restricted"),
        # ---- cloud
        _a("role-cloud-admin", "Cloud admin role", "دور مسؤول السحابة", "cloud", 5, "Full cloud administration.", "إدارة السحابة الكاملة.", exposure="restricted"),
        _a("s3-datalake", "Data lake bucket", "حاوية بحيرة البيانات", "cloud", 4, "Analytics data.", "بيانات التحليلات.", exposure="restricted"),
        _a("s3-backups", "Offsite backup bucket", "حاوية النسخ الاحتياطي", "cloud", 4, "Backup archive.", "أرشيف النسخ الاحتياطي.", exposure="restricted"),
        _a("vault", "Secrets vault", "خزنة الأسرار", "cloud", 5, "Application and deployment secrets.", "أسرار التطبيقات والنشر.", exposure="restricted", controls=["ctl-mfa"]),
        # ---- security controls (informational)
        _a("ctl-waf", "Web application firewall", "جدار حماية تطبيقات الويب", "control", 1, "Filters web traffic.", "يرشّح حركة الويب."),
        _a("ctl-fw", "Network firewall", "جدار الحماية الشبكي", "control", 1, "Network segmentation.", "تجزئة الشبكة."),
        _a("ctl-edr", "Endpoint detection agent", "عميل رصد النقاط الطرفية", "control", 1, "Endpoint monitoring.", "مراقبة النقاط الطرفية."),
        _a("ctl-mfa", "MFA gateway", "بوابة المصادقة متعددة العوامل", "control", 1, "Multi-factor sign-in.", "تسجيل دخول متعدد العوامل."),
    ]
    R = _r
    rels = [
        # --- helpdesk path (stale / excessive bastion access)
        R("r01", "u-lina", "grp-helpdesk", "member_of", "none", "validated", "Helpdesk role.", "دور مكتب المساعدة."),
        R("r02", "grp-helpdesk", "jump-host", "can_login", "admin", "validated"),                  # excessive: no recorded use
        R("r03", "jump-host", "api-orders", "admin_access", "admin", "validated", "Ops administer the orders tier.", "يدير فريق العمليات طبقة الطلبات.", True),
        R("r04", "jump-host", "backup-srv", "admin_access", "admin", "validated", "Ops administer backups.", "يدير فريق العمليات النسخ الاحتياطي."),
        R("r05", "jump-host", "dc-01", "network_access", "none", "inferred", "Admin RDP to the directory server.", "اتصال إداري بخادم الدليل.", True),
        R("r06", "jump-host", "ci-runner", "network_access", "none", "inferred", "Build administration.", "إدارة منظومة البناء."),
        R("r07", "jump-host", "app-batch", "network_access", "none", "validated", "Batch operations.", "عمليات المعالجة الدفعية."),
        R("r08", "jump-host", "file-srv", "admin_access", "admin", "validated", "Ops administer the file server.", "تدير العمليات خادم الملفات."),
        # --- application tier
        R("r09", "web-ext", "api-orders", "network_access", "none", "validated", "Portal calls the orders API.", "تستدعي البوابة واجهة الطلبات.", True),
        R("r10", "web-ext", "db-customers", "read_access", "read", "inferred"),                    # excessive: direct DB connection from the portal
        R("r11", "api-orders", "db-orders", "write_access", "write", "validated", "Order processing.", "معالجة الطلبات.", True),
        R("r12", "api-orders", "svc-app", "has_credentials", "none", "inferred"),                  # credentials in a config file
        R("r13", "svc-app", "db-customers", "read_access", "read", "validated", "Reads customer profiles for orders.", "يقرأ ملفات العملاء لمعالجة الطلبات.", True),
        R("r14", "api-orders", "app-batch", "trusts", "none", "inferred", "Trusted job submission.", "إرسال مهام موثوق."),
        R("r15", "app-batch", "s3-datalake", "write_access", "write", "validated", "ETL loads the data lake.", "تحميل بحيرة البيانات.", True),
        R("r16", "file-srv", "svc-app", "has_credentials", "none", "inferred"),                    # old script with a connection string
        # --- identity / directory
        R("r17", "dc-01", "u-khalid-it", "has_credentials", "none", "inferred"),
        R("r18", "dc-01", "svc-backup", "has_credentials", "none", "inferred"),
        R("r19", "dc-01", "svc-ci", "has_credentials", "none", "theoretical"),
        R("r20", "u-khalid-it", "grp-it-admins", "member_of", "none", "validated", "Administrator role.", "دور المسؤول."),
        R("r21", "grp-it-admins", "dc-01", "admin_access", "admin", "validated", "Directory administration.", "إدارة الدليل.", True),
        R("r22", "grp-it-admins", "jump-host", "admin_access", "admin", "validated", "Administrators use the bastion.", "يستخدم المسؤولون الخادم الوسيط."),
        R("r23", "u-khalid-it", "role-cloud-admin", "assumes_role", "admin", "validated", "Cloud administration.", "إدارة السحابة.", True),
        R("r24", "role-cloud-admin", "s3-backups", "admin_access", "admin", "validated", "Backup lifecycle management.", "إدارة دورة حياة النسخ."),
        R("r25", "role-cloud-admin", "s3-datalake", "write_access", "write", "validated", "Data lake administration.", "إدارة بحيرة البيانات."),
        R("r26", "role-cloud-admin", "vault", "read_access", "read", "validated", "Break-glass secret retrieval.", "استرجاع الأسرار في الطوارئ."),
        # --- CI/CD
        R("r27", "u-sara-dev", "grp-developers", "member_of", "none", "validated", "Developer role.", "دور المطوّر."),
        R("r28", "grp-developers", "ci-runner", "can_login", "none", "validated", "Developers trigger builds.", "يشغّل المطوّرون عمليات البناء.", True),
        R("r29", "ci-runner", "svc-ci", "has_credentials", "none", "validated"),                   # secrets in pipeline environment
        R("r30", "svc-ci", "role-cloud-admin", "assumes_role", "admin", "inferred"),               # over-privileged deploy role
        R("r31", "svc-ci", "api-orders", "admin_access", "admin", "validated", "Deployments.", "عمليات النشر.", True),
        R("r32", "ci-runner", "vault", "read_access", "read", "theoretical", "Fetch deployment secrets.", "جلب أسرار النشر."),
        # --- backup
        R("r33", "backup-srv", "svc-backup", "has_credentials", "none", "validated", "Backup agent identity.", "هوية وكيل النسخ."),
        R("r34", "svc-backup", "db-orders", "read_access", "read", "validated", "Nightly backup.", "نسخ احتياطي ليلي."),
        R("r35", "svc-backup", "db-customers", "read_access", "read", "validated", "Nightly backup.", "نسخ احتياطي ليلي."),
        R("r36", "svc-backup", "db-payroll", "read_access", "read", "validated", "Nightly backup.", "نسخ احتياطي ليلي."),
        R("r37", "svc-backup", "db-ledger", "read_access", "read", "validated", "Nightly backup.", "نسخ احتياطي ليلي."),
        R("r38", "svc-backup", "s3-backups", "write_access", "write", "validated", "Offsite copy.", "نسخة خارج الموقع."),
        # --- people with legitimate data access
        R("r39", "u-noura-dba", "db-orders", "admin_access", "admin", "validated", "DBA maintenance.", "صيانة قواعد البيانات.", True),
        R("r40", "u-noura-dba", "db-customers", "admin_access", "admin", "validated", "DBA maintenance.", "صيانة قواعد البيانات.", True),
        R("r41", "u-noura-dba", "db-payroll", "admin_access", "admin", "validated", "DBA maintenance.", "صيانة قواعد البيانات.", True),
        R("r42", "u-noura-dba", "db-ledger", "admin_access", "admin", "validated", "DBA maintenance.", "صيانة قواعد البيانات.", True),
        R("r43", "u-noura-dba", "jump-host", "can_login", "admin", "validated", "DBA maintenance access.", "وصول صيانة قواعد البيانات."),
        R("r44", "u-omar-hr", "db-payroll", "read_access", "read", "validated", "Payroll processing.", "معالجة الرواتب.", True),
        R("r45", "u-fahad-fin", "grp-finance", "member_of", "none", "validated", "Finance role.", "دور المالية."),
        R("r46", "grp-finance", "file-srv", "read_access", "read", "validated", "Finance reads shared reports.", "تقرأ المالية التقارير المشتركة."),
        R("r47", "u-fahad-fin", "db-ledger", "read_access", "read", "validated", "Ledger reporting.", "تقارير دفتر الأستاذ.", True),
        R("r48", "u-reem-exec", "db-ledger", "read_access", "read", "validated", "Board reporting.", "تقارير مجلس الإدارة."),
        # --- security controls (display only)
        R("r49", "ctl-waf", "web-ext", "protects", "none", "inferred"),
        R("r50", "ctl-fw", "web-ext", "protects", "none", "inferred"),
        R("r51", "ctl-fw", "api-orders", "protects", "none", "inferred"),
        R("r52", "ctl-edr", "jump-host", "protects", "none", "inferred"),
        R("r53", "ctl-edr", "ci-runner", "protects", "none", "inferred"),
        R("r54", "ctl-mfa", "jump-host", "protects", "none", "inferred"),
        R("r55", "ctl-mfa", "vault", "protects", "none", "inferred"),
    ]
    return Environment(name="Harbor Synthetic Logistics", name_ar="هاربر للخدمات اللوجستية (افتراضية)", assets=assets, relationships=rels)
