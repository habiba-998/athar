"""Synthetic enterprise used by the MVP. No real systems, people or data."""
from __future__ import annotations

from ..models import Asset, Environment, Relationship


def build_demo_environment() -> Environment:
    A = Asset
    R = Relationship
    assets = [
        # Identities
        A(id="emp-sara", name="Sara (Employee)", name_ar="سارة (موظفة)", type="user", criticality=1,
          compromised=True, description="Synthetic employee account assumed compromised (phished).",
          description_ar="حساب موظفة افتراضي يُفترض أنه مخترق (تصيّد)."),
        A(id="emp-omar", name="Omar (HR)", name_ar="عمر (الموارد البشرية)", type="user", criticality=2,
          description="HR analyst.", description_ar="محلل موارد بشرية."),
        A(id="grp-support", name="Support Group", name_ar="مجموعة الدعم", type="group", criticality=2,
          description="Helpdesk staff group.", description_ar="مجموعة موظفي مكتب المساعدة."),
        A(id="svc-deploy", name="Deploy Service Account", name_ar="حساب خدمة النشر", type="service_account",
          criticality=3, description="CI/CD deployment identity.", description_ar="هوية خدمة النشر المستمر."),
        A(id="admin-dba", name="DBA Admin", name_ar="مسؤول قواعد البيانات", type="user", criticality=4,
          description="Database administrator.", description_ar="مسؤول قواعد البيانات."),
        # Servers
        A(id="web-portal", name="Customer Web Portal", name_ar="بوابة العملاء", type="server", criticality=3,
          exposure="internet", controls=["fw-dmz"], description="Internet-facing portal.",
          description_ar="بوابة متاحة عبر الإنترنت."),
        A(id="app-server", name="Application Server", name_ar="خادم التطبيقات", type="server", criticality=4,
          controls=["fw-dmz"], description="Core business application.", description_ar="تطبيق الأعمال الأساسي."),
        A(id="jump-host", name="Jump Host", name_ar="خادم القفز", type="server", criticality=3,
          description="Administrative bastion.", description_ar="خادم إداري وسيط."),
        A(id="file-server", name="File Server", name_ar="خادم الملفات", type="server", criticality=2,
          description="Shared departmental files.", description_ar="ملفات الأقسام المشتركة."),
        A(id="backup-server", name="Backup Server", name_ar="خادم النسخ الاحتياطي", type="server", criticality=4,
          description="Nightly backups.", description_ar="نسخ احتياطي ليلي."),
        # Data
        A(id="db-customers", name="Customer Database", name_ar="قاعدة بيانات العملاء", type="database",
          criticality=5, exposure="restricted", description="PII and payment tokens (synthetic).",
          description_ar="بيانات شخصية ورموز دفع (افتراضية)."),
        A(id="db-hr", name="HR Database", name_ar="قاعدة بيانات الموارد البشرية", type="database",
          criticality=4, exposure="restricted", description="Payroll records (synthetic).",
          description_ar="سجلات الرواتب (افتراضية)."),
        # Cloud
        A(id="role-backup", name="Cloud Backup Role", name_ar="دور النسخ السحابي", type="cloud", criticality=3,
          description="IAM role used by backups.", description_ar="دور هوية يستخدمه النسخ الاحتياطي."),
        A(id="s3-archive", name="Backup Archive Bucket", name_ar="حاوية أرشيف النسخ", type="cloud",
          criticality=4, exposure="restricted", description="Offsite backup archive.",
          description_ar="أرشيف النسخ الاحتياطي خارج الموقع."),
        A(id="secrets-vault", name="Secrets Vault", name_ar="خزنة الأسرار", type="cloud", criticality=5,
          exposure="restricted", description="Application secrets.", description_ar="أسرار التطبيقات."),
        # Controls (informational)
        A(id="fw-dmz", name="DMZ Firewall", name_ar="جدار حماية المنطقة العازلة", type="control",
          description="Network segmentation control.", description_ar="ضابط تجزئة الشبكة."),
    ]
    rels = [
        R(id="r01", source="emp-sara", target="web-portal", type="can_login", privilege="read",
          evidence="validated", legitimate_use="Employees use the portal for daily work.",
          legitimate_use_ar="يستخدم الموظفون البوابة في العمل اليومي.", business_critical=True),
        R(id="r02", source="emp-sara", target="grp-support", type="member_of", evidence="validated",
          legitimate_use="Sara covers helpdesk shifts.", legitimate_use_ar="تغطي سارة نوبات الدعم."),
        R(id="r03", source="emp-sara", target="jump-host", type="can_login", privilege="admin",
          evidence="validated"),  # excessive: stale admin login, no justification
        R(id="r04", source="grp-support", target="file-server", type="read_access", privilege="read",
          evidence="validated", legitimate_use="Helpdesk reads shared files.",
          legitimate_use_ar="يقرأ الدعم الملفات المشتركة."),
        R(id="r05", source="file-server", target="svc-deploy", type="has_credentials", evidence="inferred"),
        R(id="r06", source="svc-deploy", target="app-server", type="admin_access", privilege="admin",
          evidence="validated", legitimate_use="Deployments need admin on the app server.",
          legitimate_use_ar="تتطلب عمليات النشر صلاحية إدارية.", business_critical=True),
        R(id="r07", source="jump-host", target="backup-server", type="admin_access", privilege="admin",
          evidence="validated", legitimate_use="Ops administer backups via the bastion.",
          legitimate_use_ar="يدير فريق العمليات النسخ عبر الخادم الوسيط."),
        R(id="r08", source="web-portal", target="app-server", type="network_access", evidence="validated",
          legitimate_use="Portal calls the application tier.", legitimate_use_ar="تستدعي البوابة طبقة التطبيقات.",
          business_critical=True),
        R(id="r09", source="app-server", target="db-customers", type="read_access", privilege="write",
          evidence="validated", legitimate_use="Application reads/writes customer records.",
          legitimate_use_ar="يقرأ التطبيق سجلات العملاء ويكتبها.", business_critical=True),
        R(id="r10", source="backup-server", target="db-customers", type="read_access", privilege="read",
          evidence="validated", legitimate_use="Nightly database dump.",
          legitimate_use_ar="تفريغ ليلي لقاعدة البيانات."),
        R(id="r11", source="app-server", target="backup-server", type="trusts", evidence="inferred"),
        R(id="r12", source="backup-server", target="role-backup", type="assumes_role", evidence="validated",
          legitimate_use="Backups upload to cloud.", legitimate_use_ar="ترفع النسخ إلى السحابة."),
        R(id="r13", source="role-backup", target="s3-archive", type="write_access", privilege="write",
          evidence="validated", legitimate_use="Backup upload.", legitimate_use_ar="رفع النسخ."),
        R(id="r14", source="app-server", target="secrets-vault", type="read_access", privilege="read",
          evidence="theoretical", legitimate_use="App fetches its own secrets.",
          legitimate_use_ar="يجلب التطبيق أسراره.", business_critical=True),
        R(id="r15", source="admin-dba", target="db-customers", type="admin_access", privilege="admin",
          evidence="validated", legitimate_use="DBA maintenance.", legitimate_use_ar="صيانة قواعد البيانات.",
          business_critical=True),
        R(id="r16", source="admin-dba", target="db-hr", type="admin_access", privilege="admin",
          evidence="validated", legitimate_use="DBA maintenance.", legitimate_use_ar="صيانة قواعد البيانات.",
          business_critical=True),
        R(id="r17", source="emp-omar", target="db-hr", type="read_access", privilege="read",
          evidence="validated", legitimate_use="HR payroll processing.", legitimate_use_ar="معالجة الرواتب.",
          business_critical=True),
        R(id="r18", source="jump-host", target="app-server", type="network_access", evidence="inferred",
          legitimate_use="Admin SSH to the app tier.", legitimate_use_ar="اتصال إداري بطبقة التطبيقات."),
        R(id="r19", source="fw-dmz", target="web-portal", type="protects"),
        R(id="r20", source="fw-dmz", target="app-server", type="protects"),
    ]
    return Environment(name="Acme Synthetic Corp", name_ar="شركة أكمي الافتراضية", assets=assets, relationships=rels)
