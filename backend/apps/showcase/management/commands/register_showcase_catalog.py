"""Idempotent Product Showcase Catalog Registration Command.

Registers all 20 corporate showcase products with meaningful descriptions,
categories, and modules. Preserves existing LMS records, connectors, credentials,
and SSO settings. Configures verified external demo URL for QBR without fabricating
links for unverified products.
"""

from typing import Any
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)

User = get_user_model()

CATALOG_PRODUCTS = [
    {
        "code": "lms",
        "name": "LMS",
        "category": "Learning & Education",
        "tagline": "Next-generation enterprise Learning Management System",
        "description": "Enterprise-grade Learning Management System powering interactive course creation, skill assessments, employee onboarding paths, progress tracking, and compliance certifications with SSO integration.",
        "overview": (
            "Enterprise-grade Learning Management System powering interactive course creation, "
            "skill assessments, employee onboarding paths, progress tracking, and compliance certifications. "
            "Integrates seamlessly with existing corporate Single Sign-On (SSO) and identity providers."
        ),
        "display_order": 1,
        "is_lms": True,
        "modules": [
            ("lms_core", "LMS Core Module", "Core LMS module for courses, assessments, and learner delivery."),
        ],
    },
    {
        "code": "hrms",
        "name": "HRMS",
        "category": "Human Resources & People Operations",
        "tagline": "Complete human resource lifecycle and workforce management",
        "description": "End-to-end HR management suite unifying employee directories, payroll processing, attendance & leaves, organizational hierarchies, performance appraisals, and employee self-service portals.",
        "overview": (
            "End-to-end HR management suite unifying employee directories, payroll processing, "
            "attendance & leaves, organizational hierarchies, performance appraisals, and employee "
            "self-service portals. Built to scale from growing organizations to large multinational enterprises."
        ),
        "display_order": 2,
        "modules": [
            ("hrms_core", "Employee Lifecycle & Records", "Centralized employee database and digital profile management."),
            ("hrms_payroll", "Payroll & Compensation", "Tax deductions, statutory compliance, and payroll generation."),
            ("hrms_attendance", "Time & Attendance", "Biometric and geo-fenced attendance with leave approval workflows."),
        ],
    },
    {
        "code": "vms-warehouse",
        "name": "VMS (Warehouse)",
        "category": "Supply Chain & Logistics",
        "tagline": "Intelligent warehouse and vendor operations management system",
        "description": "Comprehensive warehouse management system optimizing dock scheduling, inbound receiving, bin allocation, vendor delivery compliance, pick-pack-ship workflows, and real-time inventory visibility.",
        "overview": (
            "Comprehensive warehouse management system optimizing dock scheduling, inbound receiving, "
            "bin allocation, vendor delivery compliance, pick-pack-ship workflows, and real-time inventory visibility. "
            "Reduces turnaround times and maximizes warehouse space utilization."
        ),
        "display_order": 3,
        "modules": [
            ("vms_inbound", "Inbound & Dock Scheduling", "Vendor appointments, yard management, and dock scheduling."),
            ("vms_warehouse_ops", "Storage & Bin Allocation", "Intelligent bin location allocation and put-away rules."),
            ("vms_fulfillment", "Outbound Fulfillment", "Pick-pack-ship pipelines, barcode validation, and dispatch logs."),
        ],
    },
    {
        "code": "leasing",
        "name": "Leasing",
        "category": "Real Estate & Asset Management",
        "tagline": "Commercial and asset lease lifecycle management platform",
        "description": "Modern lease administration software designed for property portfolios and high-value equipment assets. Automates contract drafting, escalation clauses, milestone billing, renewals, tenant communication, and compliance.",
        "overview": (
            "Modern lease administration software designed for commercial real estate portfolios "
            "and high-value equipment assets. Automates contract drafting, escalation clauses, "
            "milestone billing, renewals, tenant communications, and statutory IFRS 16 lease accounting compliance."
        ),
        "display_order": 4,
        "modules": [
            ("leasing_contracts", "Contract Management", "Digital lease contracts, terms, escalation clauses, and amendments."),
            ("leasing_billing", "Billing & Invoicing", "Automated periodic rent invoicing and utility pass-throughs."),
            ("leasing_tenants", "Tenant & Asset Portal", "Tenant self-service, maintenance requests, and insurance tracking."),
        ],
    },
    {
        "code": "fieldsense",
        "name": "FieldSense Operations Hub",
        "category": "Field Operations & Workforce",
        "tagline": "Intelligent field force tracking, route optimization, and activity logging",
        "description": "Real-time field force automation and tracking platform. Empowers mobile teams with GPS-enabled task allocation, automated geo-fenced attendance, route optimization, real-time beat plans, and client visit reporting.",
        "overview": (
            "Real-time field force automation and tracking platform. Empowers field representatives "
            "and managers with GPS-enabled task allocation, automated geo-fenced attendance, "
            "route optimization, dynamic beat planning, and structured client visit logging."
        ),
        "display_order": 5,
        "is_fieldops_child": True,
        "modules": [
            ("fieldsense_tracking", "Location & Beat Planning", "Live GPS tracking, route deviation alerts, and daily travel logs."),
            ("fieldsense_tasks", "Field Task Allocation", "Dynamic dispatching of service tasks and delivery assignments."),
            ("fieldsense_reporting", "Visit & Activity Reports", "Client meeting checklists, signature capture, and photographic proof."),
        ],
    },
    {
        "code": "inventory",
        "name": "INVENTORY",
        "category": "Supply Chain & Logistics",
        "tagline": "Enterprise stock control, multi-warehouse tracking, and valuation",
        "description": "Multi-location inventory tracking and stock management system. Features automated reorder points, batch/serial tracking, stock transfers, barcode scanning, valuation ledgers, and audit-ready discrepancy logs.",
        "overview": (
            "Multi-location inventory tracking and stock control system. Provides end-to-end visibility "
            "with batch/serial tracking, automated reorder thresholds, inter-warehouse transfers, "
            "landed cost calculations, and perpetual inventory valuation audits."
        ),
        "display_order": 6,
        "modules": [
            ("inv_stock_control", "Stock Ledger & Valuations", "FIFO, LIFO, and weighted average stock accounting ledgers."),
            ("inv_multi_warehouse", "Multi-Location Tracking", "Transfers, transit tracking, and cross-warehouse balances."),
            ("inv_reorder", "Demand & Reorder Automation", "Predictive safety stock alerts and automated replenishment."),
        ],
    },
    {
        "code": "crm-logicon",
        "name": "CRM (Logicon)",
        "category": "Sales & Customer Relationship",
        "tagline": "Logicon intelligent customer relationship and lead management",
        "description": "Tailored CRM engine designed for logistics and high-velocity B2B sales teams. Features lead capture, pipeline scoring, account management, interaction logs, quote generation, and deal conversion workflows.",
        "overview": (
            "Logicon CRM is an intelligent relationship management platform designed for modern enterprise sales. "
            "Includes end-to-end lead ingestion, automated qualification scoring, multi-tier account hierarchies, "
            "communication timelines, and rapid quote generation."
        ),
        "display_order": 7,
        "is_fieldops_child": True,
        "modules": [
            ("crm_pipeline", "Lead & Opportunity Pipeline", "Visual Kanban stages, win probability scoring, and stage gating."),
            ("crm_accounts", "Account & Contact Management", "360-degree account timelines and contact relationship graphs."),
            ("crm_quotes", "Quote & Proposal Generator", "Rate card integration, price calculation, and PDF quote generation."),
        ],
    },
    {
        "code": "mom",
        "name": "MOM",
        "category": "Productivity & Collaboration",
        "tagline": "Minutes of Meeting management and automated action item tracking",
        "description": "Structured corporate meeting governance platform. Streamlines agenda creation, automated audio transcription notes, attendee attendance, action-item delegation with deadlines, and instant stakeholder distribution.",
        "overview": (
            "Corporate meeting governance and productivity platform. Converts messy conversations into "
            "structured, accountable results with formal agenda creation, action-item assignment, automated "
            "reminders, progress tracking, and searchable historical minutes."
        ),
        "display_order": 8,
        "modules": [
            ("mom_agendas", "Agenda & Meeting Scheduler", "Pre-meeting collaboration, calendar sync, and objective alignment."),
            ("mom_minutes", "Action Items & Task Tracker", "Assigned tasks with due dates, dependencies, and escalation."),
            ("mom_distribution", "Stakeholder Distribution", "One-click minutes sign-off and multi-channel notification."),
        ],
    },
    {
        "code": "qbr",
        "name": "QBR — Excel Reports",
        "category": "Analytics & Executive Reporting",
        "visibility": ShowcaseVisibility.HIDDEN,
        "tagline": "Interactive quarterly business reviews with instant Excel analytics and charting",
        "description": "Automated Quarterly Business Review platform allowing users to upload quarterly business Excel and CSV files to instantly generate executive graphs, charts, variance analysis, and presentation-ready PDF reports.",
        "overview": (
            "QBR — Excel Reports transforms raw quarterly business spreadsheets into interactive executive "
            "dashboards and reports. Users drag-and-drop quarterly Excel workbooks to instantly generate "
            "comparative bar charts, trend lines, KPI scorecards, and boardroom-ready presentation decks. "
            "Includes a verified interactive live demo environment."
        ),
        "display_order": 9,
        "demo_url": "https://excelreports.vibecopilot.ai/",
        "demo_env_name": "QBR Live Web Demo",
        "demo_description": "Interactive web demo allowing users to upload sample QBR Excel files and generate real-time graphs.",
        "modules": [
            ("qbr_excel_engine", "Excel Parser & Data Extraction", "Fast client-side parsing of XLSX and CSV quarterly files."),
            ("qbr_charts", "Interactive Graph & Chart Engine", "Comparative quarterly performance graphs, margins, and trends."),
            ("qbr_reports", "Executive PDF & Presentation Export", "One-click export to branded executive presentation documents."),
        ],
    },
    {
        "code": "audit-smart",
        "name": "AUDIT SMART",
        "category": "Compliance, Audit & Quality",
        "tagline": "Digital audit workflows, risk inspections, and compliance management",
        "description": "Smart audit automation tool for internal reviews, statutory audits, and safety inspections. Features standardized checklists, digital evidence collection, non-conformance tracking, corrective action plans (CAPA), and scorecards.",
        "overview": (
            "Smart compliance and audit platform ensuring continuous operational excellence. "
            "Eliminates paper checklists with standardized digital inspection templates, mobile photo evidence, "
            "automated non-conformance scoring, and corrective and preventive action (CAPA) tracking."
        ),
        "display_order": 10,
        "modules": [
            ("audit_checklists", "Inspection Checklists & Templates", "Customizable inspection trees with risk weightings."),
            ("audit_capa", "Non-Conformance & CAPA", "Corrective action tracking with assigned root cause investigations."),
            ("audit_analytics", "Risk & Compliance Scoring", "Facility audit scorecards and compliance health trends."),
        ],
    },
    {
        "code": "vendor-invoice-management",
        "name": "Vendor & Invoice Management",
        "category": "Finance & Procurement",
        "tagline": "Procure-to-pay automation, vendor onboarding, and 3-way invoice matching",
        "description": "End-to-end procurement and payable processing platform. Streamlines supplier onboarding, purchase order validation, automated OCR invoice scanning, 3-way matching, approval matrices, and payment disbursement scheduling.",
        "overview": (
            "Procure-to-pay automation platform connecting finance, procurement, and external suppliers. "
            "Features automated optical character recognition (OCR) for incoming invoices, "
            "three-way purchase order matching, multi-tier approval matrices, and payment schedule reconciliation."
        ),
        "display_order": 11,
        "modules": [
            ("vim_vendor_portal", "Vendor Onboarding & KYC", "Supplier registration, compliance document collection, and verification."),
            ("vim_invoice_ocr", "OCR & 3-Way Matching", "Automatic invoice extraction matched against POs and receiving slips."),
            ("vim_approvals", "Approval Workflows & Payments", "Configurable delegation of financial authorities and payment batches."),
        ],
    },
    {
        "code": "quiz",
        "name": "QUIZ",
        "category": "Learning & Education",
        "tagline": "Interactive assessments, timed knowledge checks, and certifications",
        "description": "Dynamic evaluation engine supporting timed quizzes, randomized question banks, multimedia questions, instant grading, anti-cheating timers, and skill-certification badges for teams and academies.",
        "overview": (
            "Interactive assessment and testing platform designed for corporate compliance, product training, "
            "and talent evaluations. Supports question bank randomization, timed exam sessions, "
            "instant scoring, and verifiable digital completion badges."
        ),
        "display_order": 12,
        "modules": [
            ("quiz_question_bank", "Question Bank & Tagging", "Taxonomy-based question libraries with difficulty ratings."),
            ("quiz_engine", "Timed Assessment Runner", "Secure testing window with randomized order and automatic timeouts."),
            ("quiz_analytics", "Candidate Grading & Reports", "Cohort analysis, score distributions, and gap identification."),
        ],
    },
    {
        "code": "workshop-trinity",
        "name": "WORKSHOP (Trinity)",
        "category": "Service & Field Operations",
        "tagline": "Trinity automotive and equipment service workshop management",
        "description": "All-in-one workshop and garage management system. Controls job card generation, mechanic time allocations, spare parts requisitions, vehicle inspection checklists, repair cost estimations, and automated customer status alerts.",
        "overview": (
            "Specialized service workshop operations system for automotive, machinery, and fleet repair hubs. "
            "Digitizes the entire repair floor with digital job cards, technician task allocations, "
            "parts store requisitions, estimate approvals, and automated customer progress updates."
        ),
        "display_order": 13,
        "modules": [
            ("trinity_job_cards", "Job Card & Intake Management", "Vehicle intake, fault diagnostics, and customer estimate authorizations."),
            ("trinity_spares", "Spare Parts & Inventory Billing", "Real-time stock pick lists and billing item integration."),
            ("trinity_service_ops", "Technician Scheduling & Quality Checks", "Bay scheduling, technician time tracking, and final quality checks."),
        ],
    },
    {
        "code": "fieldops",
        "name": "FIELDOPS",
        "category": "Enterprise Operations Suite",
        "tagline": "Integrated enterprise suite unifying CRM, Sales Tracker, and FIELDSENCE",
        "description": "Unified operations suite engineered for high-performance field organizations. Seamlessly connects Logicon CRM, Sales Tracker pipeline analytics, and FIELDSENCE geo-tracking into a single command center with cross-functional executive dashboards.",
        "overview": (
            "FIELDOPS is an integrated operations suite uniting CRM (Logicon), Sales Tracker, "
            "and FIELDSENCE into a unified command plane. Designed for large distributed sales and field "
            "forces, FIELDOPS connects customer inquiries to field representative dispatch, sales progress, "
            "and executive revenue forecasting with zero data silos."
        ),
        "display_order": 14,
        "is_suite": True,
        "modules": [
            ("fieldops_crm", "Logicon CRM Module", "Integrated customer acquisition and lead lifecycle module."),
            ("fieldops_sales", "Sales Tracker Module", "Revenue quota, deal closure, and performance tracking module."),
            ("fieldops_fieldsense", "FieldSense Field Force Module", "Live mobile workforce dispatch, beat plans, and geo-tracking module."),
        ],
    },
    {
        "code": "workhub",
        "name": "WORKHUB",
        "category": "Productivity & Collaboration",
        "tagline": "Centralized workplace collaboration, Kanban boards, and project workspaces",
        "description": "Digital workspace uniting internal teams with agile Kanban boards, document co-authoring, project milestone trackers, cross-department communication channels, and real-time operational feeds.",
        "overview": (
            "Central operational workspace for modern teams. Combines project boards, sprint backlogs, "
            "document wikis, discussion threads, and operational milestone tracking into a single "
            "intuitive collaborative environment."
        ),
        "display_order": 15,
        "modules": [
            ("workhub_projects", "Agile Boards & Task Tracking", "Kanban and list views with WIP limits and sprint horizons."),
            ("workhub_docs", "Document Collaboration", "Structured rich-text team wikis and project specifications."),
            ("workhub_channels", "Team Communication & Announcements", "Contextual comment feeds and company-wide bulletin boards."),
        ],
    },
    {
        "code": "ai-dashboard",
        "name": "AI DASHBOARD",
        "category": "AI & Business Intelligence",
        "tagline": "Predictive enterprise intelligence, KPI tracking, and generative insights",
        "description": "Next-generation executive BI dashboard powered by machine learning models. Delivers anomaly detection, predictive sales forecasting, operational bottleneck identification, and natural language query interfaces.",
        "overview": (
            "Executive business intelligence platform augmented with machine learning. Aggregates data "
            "across all enterprise operational modules to provide predictive trends, automated variance explanations, "
            "financial forecasting models, and natural language data exploration."
        ),
        "display_order": 16,
        "modules": [
            ("ai_analytics_engine", "Predictive KPI Models", "Time-series forecasting, revenue trajectories, and variance detection."),
            ("ai_nl_queries", "Natural Language Data Queries", "Chat-based query engine transforming questions into chart visualizations."),
            ("ai_visualizations", "Executive Visual Dashboards", "Configurable widget canvases with real-time KPI health indicators."),
        ],
    },
    {
        "code": "event-module",
        "name": "EVENT MODULE",
        "category": "Events & Corporate Engagement",
        "tagline": "End-to-end corporate event planning, registration, and attendee management",
        "description": "Comprehensive platform for virtual, hybrid, and in-person corporate events. Handles landing page creation, ticket registrations, speaker agendas, QR-code entry check-ins, live attendee polling, and post-event analytics.",
        "overview": (
            "Complete event lifecycle solution designed for corporate conferences, trade exhibitions, "
            "and partner summits. Encompasses branded registration portals, automated ticketing, "
            "speaker itineraries, fast QR check-in desks, and attendee engagement tracking."
        ),
        "display_order": 17,
        "modules": [
            ("event_registration", "Registration & Ticketing", "Custom registration fields, ticket classes, and badge generation."),
            ("event_agenda", "Speaker & Session Schedules", "Multi-track schedules with speaker profiles and room assignments."),
            ("event_checkin", "QR Check-In & Badging", "Mobile camera QR scanning and real-time hall attendance metrics."),
        ],
    },
    {
        "code": "video-content-generation",
        "name": "VIDEO CONTENT GENERATION",
        "category": "AI & Media Studio",
        "tagline": "AI-driven automated video generation and marketing media studio",
        "description": "State-of-the-art AI video studio allowing corporate teams to generate marketing videos, training clips, product teasers, and localized multilingual avatars from text scripts within minutes.",
        "overview": (
            "Generative AI media studio empowering marketing and training teams to produce high-impact "
            "videos in minutes. Features text-to-speech synthesis in over 40 languages, realistic digital presenters, "
            "automated scene sequencing, branded lower-thirds, and automated subtitle burnt-in."
        ),
        "display_order": 18,
        "modules": [
            ("video_scripting", "Script-to-Video Engine", "AI storyboard generation, caption extraction, and scene composition."),
            ("video_avatars", "AI Avatars & Voice Synthesis", "Photorealistic presenter avatars with accurate lip-sync and tone control."),
            ("video_templates", "Brand Templates & Exports", "Brand asset watermarking, aspect ratio conversions, and 4K rendering."),
        ],
    },
    {
        "code": "ats",
        "name": "ATS",
        "category": "Human Resources & People Operations",
        "tagline": "Intelligent Applicant Tracking System and recruitment pipeline engine",
        "description": "Collaborative hiring and applicant tracking software. Features resume parsing, candidate scoring, interview scheduling integrations, scorecard evaluations, background check workflows, and automated offer letter generation.",
        "overview": (
            "Modern talent acquisition platform streamlining the entire recruiting pipeline from job requisitions "
            "to offer letter acceptance. Includes automated resume parsing, AI candidate match scoring, "
            "interviewer scorecards, automated calendar booking, and pre-boarding document collection."
        ),
        "display_order": 19,
        "modules": [
            ("ats_job_board", "Job Openings & Candidate Portal", "One-click job distribution and candidate application portal."),
            ("ats_resume_parser", "Resume Parsing & Match Scoring", "Skills extraction, experience calculation, and suitability rating."),
            ("ats_interviews", "Interview Scheduling & Scorecards", "Calendar integrations, standardized grading criteria, and offer letters."),
        ],
    },
    {
        "code": "sales-tracker",
        "name": "SALES TRACKER",
        "category": "Sales & Customer Relationship",
        "tagline": "Target tracking, rep quotas, revenue forecasting, and deal closure analytics",
        "description": "High-visibility revenue and performance tracking system for sales leadership. Tracks individual quotas, conversion velocity, commission calculations, territory benchmarks, and dynamic sales leaderboards.",
        "overview": (
            "Sales execution and incentive management software providing leaders with total visibility "
            "into quota achievement, conversion cycles, territory productivity, and commission structures. "
            "Integrates directly with CRM deals to eliminate spreadsheet compensation calculations."
        ),
        "display_order": 20,
        "is_fieldops_child": True,
        "modules": [
            ("sales_quotas", "Quota & Target Setting", "Hierarchical revenue targets, individual rep quotas, and pacing metrics."),
            ("sales_forecasting", "Revenue Forecasting & Pipeline Velocity", "Weighted forecast models and stage bottleneck analysis."),
            ("sales_commissions", "Commission & Incentives Ledger", "Automated commission tier calculation and payout statements."),
        ],
    },
]


class Command(BaseCommand):
    help = "Idempotently register the complete product showcase catalog with categories, modules, and QBR demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate registration without persisting changes.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run", False)
        self.stdout.write("Starting idempotent product showcase catalog registration...")

        owner = (
            User.objects.filter(is_platform_owner=True).order_by("created_at").first()
            or User.objects.filter(is_superuser=True).first()
            or User.objects.first()
        )
        if not owner:
            self.stderr.write(self.style.ERROR("No user found to act as creator for products."))
            return

        with transaction.atomic():
            fieldops_product = None
            registered_count = 0
            updated_count = 0

            # 1. First pass: ensure all products exist
            created_products = {}
            for item in CATALOG_PRODUCTS:
                code = item["code"]
                existing_product = Product.objects.filter(code=code).first()
                if not existing_product and code in ("fieldsense", "fieldsence"):
                    alt_code = "fieldsence" if code == "fieldsense" else "fieldsense"
                    existing_product = Product.objects.filter(code=alt_code).first()
                    if existing_product and code == "fieldsense":
                        existing_product.code = "fieldsense"
                        existing_product.name = item["name"]
                        existing_product.save(update_fields=["code", "name"])

                if existing_product:
                    # Preserve existing record! Never overwrite status if active, never overwrite existing custom values
                    product = existing_product
                    updated = False
                    if not product.description and item.get("description"):
                        product.description = item["description"]
                        updated = True
                    if updated:
                        product.save(update_fields=["description"])
                        updated_count += 1
                    self.stdout.write(f"Product exists: {product.name} ({code}) [Preserved]")
                else:
                    product = Product.objects.create(
                        code=code,
                        name=item["name"],
                        description=item["description"],
                        status=ProductStatus.ACTIVE,
                        created_by=owner,
                        updated_by=owner,
                    )
                    registered_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Registered product: {product.name} ({code})"))

                created_products[code] = product
                if code == "fieldops":
                    fieldops_product = product

            # 2. Second pass: link FIELDOPS sub-products if suite schema allows
            if fieldops_product and hasattr(Product, "parent"):
                for item in CATALOG_PRODUCTS:
                    if item.get("is_fieldops_child"):
                        prod = created_products.get(item["code"])
                        if prod and getattr(prod, "parent_id", None) != fieldops_product.id:
                            prod.parent = fieldops_product
                            prod.save(update_fields=["parent"])
                            self.stdout.write(f"Linked {prod.code} as sub-product under FIELDOPS suite.")

            # 3. Third pass: modules registration
            for item in CATALOG_PRODUCTS:
                prod = created_products[item["code"]]
                for idx, (m_code, m_name, m_desc) in enumerate(item.get("modules", [])):
                    mod = ProductModule.objects.filter(product=prod, code=m_code).first()
                    if not mod and ("fieldsense" in m_code or "fieldsence" in m_code):
                        alt_mod = m_code.replace("fieldsense", "fieldsence") if "fieldsense" in m_code else m_code.replace("fieldsence", "fieldsense")
                        mod = ProductModule.objects.filter(product=prod, code=alt_mod).first()
                        if mod and "fieldsense" in m_code:
                            mod.code = m_code
                            mod.name = m_name
                            mod.save(update_fields=["code", "name"])
                    if not mod:
                        ProductModule.objects.create(
                            product=prod,
                            code=m_code,
                            name=m_name,
                            description=m_desc,
                            display_order=idx,
                            status=CatalogStatus.ACTIVE,
                            created_by=owner,
                            updated_by=owner,
                        )

            # 4. Fourth pass: Showcase profiles
            for item in CATALOG_PRODUCTS:
                prod = created_products[item["code"]]
                profile = ProductShowcaseProfile.objects.filter(product=prod).first()
                target_visibility = item.get("visibility", ShowcaseVisibility.PUBLISHED)

                if not profile:
                    profile = ProductShowcaseProfile.objects.create(
                        product=prod,
                        tagline=item["tagline"],
                        overview=item["overview"],
                        category=item["category"],
                        visibility=target_visibility,
                        display_order=item["display_order"],
                        created_by=owner,
                        updated_by=owner,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created showcase profile for: {prod.name} (Category: {item['category']}, Visibility: {target_visibility})"))
                else:
                    # Update category, display_order, and visibility if specified
                    updates = []
                    if not profile.category and item.get("category"):
                        profile.category = item["category"]
                        updates.append("category")
                    if profile.display_order == 0 and item.get("display_order"):
                        profile.display_order = item["display_order"]
                        updates.append("display_order")
                    if item.get("visibility") and profile.visibility != item["visibility"]:
                        profile.visibility = item["visibility"]
                        updates.append("visibility")
                    elif profile.visibility == ShowcaseVisibility.DRAFT and not item.get("is_lms"):
                        profile.visibility = ShowcaseVisibility.PUBLISHED
                        updates.append("visibility")
                    if updates:
                        profile.save(update_fields=updates)
                        self.stdout.write(f"Updated showcase profile fields {updates} for: {prod.name}")

            # 5. Fifth pass: Configure QBR demo environment and launch configuration
            qbr_prod = created_products.get("qbr")
            if qbr_prod:
                qbr_profile = ProductShowcaseProfile.objects.filter(product=qbr_prod).first()
                demo_url = "https://excelreports.vibecopilot.ai/"
                env = ProductDemoEnvironment.objects.filter(product=qbr_prod, base_url=demo_url).first()
                if not env:
                    env = ProductDemoEnvironment.objects.create(
                        product=qbr_prod,
                        name="QBR Live Web Demo",
                        base_url=demo_url,
                        description="Interactive web demo allowing users to upload sample QBR Excel files and generate real-time graphs.",
                        is_active=True,
                        created_by=owner,
                        updated_by=owner,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created QBR Demo Environment: {demo_url}"))
                elif not env.is_active:
                    env.is_active = True
                    env.save(update_fields=["is_active"])

                qbr_launch_cfg = ProductLaunchConfig.objects.filter(product=qbr_prod).first()
                if not qbr_launch_cfg:
                    ProductLaunchConfig.objects.create(
                        product=qbr_prod,
                        profile=qbr_profile,
                        launch_mode=ProductLaunchConfig.LaunchMode.DEMO_ONLY,
                        target_environment=env,
                        allowed_targets=[demo_url],
                        policy={},
                        notes="Configured standalone live external demo for marketing presentations.",
                        created_by=owner,
                        updated_by=owner,
                    )
                    self.stdout.write(self.style.SUCCESS("Configured QBR ProductLaunchConfig for DEMO_ONLY mode."))
                else:
                    # Preserve existing launch config if already customized, ensure active environment is linked
                    if qbr_launch_cfg.launch_mode != ProductLaunchConfig.LaunchMode.DEMO_ONLY:
                        qbr_launch_cfg.launch_mode = ProductLaunchConfig.LaunchMode.DEMO_ONLY
                        qbr_launch_cfg.target_environment = env
                        if demo_url not in qbr_launch_cfg.allowed_targets:
                            qbr_launch_cfg.allowed_targets = [demo_url]
                        qbr_launch_cfg.save(update_fields=["launch_mode", "target_environment", "allowed_targets"])
                        self.stdout.write("Updated QBR launch configuration to DEMO_ONLY mode.")

            # 5b. Configure HRMS (PeoplePulse) live sandbox demo environment and launch configuration
            hrms_prod = created_products.get("hrms")
            if hrms_prod:
                hrms_profile = ProductShowcaseProfile.objects.filter(product=hrms_prod).first()
                hrms_demo_url = "https://hrms.vibesandbox.live"
                hrms_env = ProductDemoEnvironment.objects.filter(product=hrms_prod, base_url=hrms_demo_url).first()
                if not hrms_env:
                    hrms_env = ProductDemoEnvironment.objects.create(
                        product=hrms_prod,
                        name="PeoplePulse HRMS Sandbox",
                        base_url=hrms_demo_url,
                        description="Live PeoplePulse HRMS demonstration sandbox featuring employee directory, attendance, and organizational departments.",
                        is_active=True,
                        created_by=owner,
                        updated_by=owner,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created HRMS Demo Environment: {hrms_demo_url}"))
                elif not hrms_env.is_active:
                    hrms_env.is_active = True
                    hrms_env.save(update_fields=["is_active"])

                hrms_launch_cfg = ProductLaunchConfig.objects.filter(product=hrms_prod).first()
                if not hrms_launch_cfg:
                    ProductLaunchConfig.objects.create(
                        product=hrms_prod,
                        profile=hrms_profile,
                        launch_mode=ProductLaunchConfig.LaunchMode.DEMO_ONLY,
                        target_environment=hrms_env,
                        allowed_targets=[hrms_demo_url],
                        policy={"open_mode": "embed", "allow_iframe": True},
                        notes="Live PeoplePulse HRMS sandbox environment for showcase presentations.",
                        created_by=owner,
                        updated_by=owner,
                    )
                    self.stdout.write(self.style.SUCCESS("Configured HRMS ProductLaunchConfig for DEMO_ONLY mode."))
                else:
                    changed_fields = []
                    if hrms_launch_cfg.launch_mode != ProductLaunchConfig.LaunchMode.DEMO_ONLY:
                        hrms_launch_cfg.launch_mode = ProductLaunchConfig.LaunchMode.DEMO_ONLY
                        changed_fields.append("launch_mode")
                    if hrms_launch_cfg.target_environment != hrms_env:
                        hrms_launch_cfg.target_environment = hrms_env
                        changed_fields.append("target_environment")
                    if hrms_demo_url not in hrms_launch_cfg.allowed_targets:
                        hrms_launch_cfg.allowed_targets = [hrms_demo_url]
                        changed_fields.append("allowed_targets")
                    hrms_policy = hrms_launch_cfg.policy or {}
                    if hrms_policy.get("open_mode") != "embed" or not hrms_policy.get("allow_iframe"):
                        hrms_policy["open_mode"] = "embed"
                        hrms_policy["allow_iframe"] = True
                        hrms_launch_cfg.policy = hrms_policy
                        changed_fields.append("policy")
                    if changed_fields:
                        hrms_launch_cfg.save(update_fields=changed_fields)
                        self.stdout.write(f"Updated HRMS launch configuration ({changed_fields}) to DEMO_ONLY embed mode.")

            # 5c. Configure VMS (WarehouseOS) live sandbox demo environment and launch configuration
            vms_prod = created_products.get("vms-warehouse")
            if vms_prod:
                vms_profile = ProductShowcaseProfile.objects.filter(product=vms_prod).first()
                vms_demo_url = "https://vms.vibecopilot.ai"
                vms_env = ProductDemoEnvironment.objects.filter(product=vms_prod, base_url=vms_demo_url).first()
                if not vms_env:
                    vms_env = ProductDemoEnvironment.objects.create(
                        product=vms_prod,
                        name="WarehouseOS VMS Sandbox",
                        base_url=vms_demo_url,
                        description="Live WarehouseOS VMS demonstration sandbox featuring dock scheduling, real-time inventory, and wave operations.",
                        is_active=True,
                        created_by=owner,
                        updated_by=owner,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created VMS Demo Environment: {vms_demo_url}"))
                elif not vms_env.is_active:
                    vms_env.is_active = True
                    vms_env.save(update_fields=["is_active"])

                vms_launch_cfg = ProductLaunchConfig.objects.filter(product=vms_prod).first()
                if not vms_launch_cfg:
                    ProductLaunchConfig.objects.create(
                        product=vms_prod,
                        profile=vms_profile,
                        launch_mode=ProductLaunchConfig.LaunchMode.DEMO_ONLY,
                        target_environment=vms_env,
                        allowed_targets=[vms_demo_url],
                        policy={"open_mode": "embed", "allow_iframe": False, "in_window_demo": True},
                        notes="Live WarehouseOS VMS sandbox environment for showcase presentations.",
                        created_by=owner,
                        updated_by=owner,
                    )
                    self.stdout.write(self.style.SUCCESS("Configured VMS ProductLaunchConfig for DEMO_ONLY mode."))
                else:
                    changed_fields = []
                    if vms_launch_cfg.launch_mode != ProductLaunchConfig.LaunchMode.DEMO_ONLY:
                        vms_launch_cfg.launch_mode = ProductLaunchConfig.LaunchMode.DEMO_ONLY
                        changed_fields.append("launch_mode")
                    if vms_launch_cfg.target_environment != vms_env:
                        vms_launch_cfg.target_environment = vms_env
                        changed_fields.append("target_environment")
                    if vms_demo_url not in vms_launch_cfg.allowed_targets:
                        vms_launch_cfg.allowed_targets = [vms_demo_url]
                        changed_fields.append("allowed_targets")
                    vms_policy = vms_launch_cfg.policy or {}
                    if vms_policy.get("open_mode") != "embed" or not vms_policy.get("in_window_demo"):
                        vms_policy["open_mode"] = "embed"
                        vms_policy["in_window_demo"] = True
                        vms_launch_cfg.policy = vms_policy
                        changed_fields.append("policy")
                    if changed_fields:
                        vms_launch_cfg.save(update_fields=changed_fields)
                        self.stdout.write(f"Updated VMS launch configuration ({changed_fields}) to DEMO_ONLY embed mode.")

            # 6. Sixth pass: Non-demo products must not have misleading active demo links
            for item in CATALOG_PRODUCTS:
                code = item["code"]
                if code in ("qbr", "lms", "hrms", "vms-warehouse", "fieldsense", "fieldsence", "workshop-trinity"):
                    continue
                prod = created_products[code]
                profile = ProductShowcaseProfile.objects.filter(product=prod).first()
                launch_cfg = ProductLaunchConfig.objects.filter(product=prod).first()
                if not launch_cfg:
                    # Explicitly set launch_mode to DISABLED so catalog availability is distinguished from demo readiness
                    ProductLaunchConfig.objects.create(
                        product=prod,
                        profile=profile,
                        launch_mode=ProductLaunchConfig.LaunchMode.DISABLED,
                        target_environment=None,
                        allowed_targets=[],
                        policy={},
                        notes="Demo environment pending validation. Product catalog profile available for review.",
                        created_by=owner,
                        updated_by=owner,
                    )

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("Dry-run complete. All database changes rolled back."))
            else:
                self.stdout.write(self.style.SUCCESS(f"Successfully finished catalog registration: {len(CATALOG_PRODUCTS)} products verified in showcase."))
