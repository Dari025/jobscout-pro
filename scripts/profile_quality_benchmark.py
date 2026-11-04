"""Broader adversarial profile benchmark for the role-ranking engine.

All CVs and vacancies are synthetic. This suite deliberately includes
near-matches, title-only matches, seniority mismatches and generic words.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from jobscout_links import professional_domain_mismatch, score_job


PROFILES = [
    ("Economics graduate / junior data", "Economics graduate. Econometrics, statistics, Excel, R, beginner Python and SQL. University projects in forecasting and business analysis.", "Junior Data Analyst",
     [("Junior Data Analyst", "SQL reporting, dashboards and business metrics.", "GOOD"),
      ("Senior Data Scientist", "Machine learning, Python, model deployment, 8 years experience.", "BAD"),
      ("Marketing Data Analyst", "Marketing campaign analytics, attribution, customer segments.", "ADJACENT"),
      ("Geologist", "Geology, hydrogeology, mineral exploration.", "BAD")]),
    ("Hydrogeologist", "Hydrogeologist with groundwater modelling, aquifer assessment, field sampling, GIS, environmental impact and geology.", "Hydrogeologist",
     [("Hydrogeologist", "Groundwater modelling, aquifer assessment, field surveys.", "GOOD"),
      ("Senior Geologist", "Geological mapping, mineral exploration and resource estimation.", "ADJACENT"),
      ("Oncology Research Scientist", "Research, scientific reporting, multidisciplinary work and clinical trials.", "BAD"),
      ("Team Leader", "Retail store operations, sales targets and staff scheduling.", "BAD")]),
    ("Clinical research professional", "Clinical research coordinator with GCP, clinical trials, patient recruitment, regulatory documentation, oncology and pharmacovigilance.", "Clinical Research Coordinator",
     [("Clinical Research Coordinator", "Clinical trials, GCP, patient recruitment and regulatory documentation.", "GOOD"),
      ("Research Coordinator", "University research administration and grant reporting.", "ADJACENT"),
      ("Research Scientist", "Scientific research, analysis and project leadership.", "ADJACENT"),
      ("Geoscientist", "Geology and geochemistry field research.", "BAD")]),
    ("Software engineer", "Backend software engineer. Python, Java, REST APIs, PostgreSQL, Docker, AWS, CI/CD, unit testing and distributed systems.", "Backend Software Engineer",
     [("Backend Software Engineer", "Python, APIs, PostgreSQL, Docker and distributed services.", "GOOD"),
      ("Senior Software Architect", "Enterprise architecture, strategic planning and 12 years experience.", "BAD"),
      ("Data Analyst", "SQL, reports, spreadsheets and dashboards.", "ADJACENT"),
      ("IT Support Technician", "Desktop support, Windows, printers and helpdesk.", "ADJACENT")]),
    ("Environmental scientist", "Environmental scientist with environmental impact assessment, ecology, biodiversity, conservation, GIS, water quality and environmental regulation.", "Environmental Scientist",
     [("Environmental Scientist", "Environmental impact assessment, ecology, biodiversity and GIS.", "GOOD"),
      ("Environmental Engineer", "Wastewater, environmental permits, treatment plant design.", "ADJACENT"),
      ("Clinical Scientist", "Clinical laboratory diagnostics and biomedical studies.", "BAD"),
      ("Sustainability Manager", "ESG reporting, corporate sustainability and compliance.", "ADJACENT")]),
    ("Lawyer", "Qualified lawyer. Spanish civil and commercial law, contracts, litigation, legal research, regulatory compliance and GDPR.", "Legal Counsel",
     [("Legal Counsel", "Commercial contracts, regulatory advice and corporate legal matters.", "GOOD"),
      ("Compliance Analyst", "Regulatory compliance, internal controls, policy monitoring.", "ADJACENT"),
      ("Data Protection Officer", "GDPR, privacy and regulatory governance.", "ADJACENT"),
      ("Financial Analyst", "Financial modelling, equity valuation and forecasting.", "BAD")]),
    ("Finance analyst", "Financial analyst with financial modelling, valuation, Excel, budgeting, forecasting, accounting and management reporting.", "Financial Analyst",
     [("Financial Analyst", "Budgeting, forecasting, financial models and reporting.", "GOOD"),
      ("Investment Analyst", "Equity research, valuation, portfolio management and capital markets.", "ADJACENT"),
      ("Data Analyst", "Data quality, dashboards, SQL and KPIs.", "ADJACENT"),
      ("Clinical Data Analyst", "Clinical trial datasets, patient records and biostatistics.", "BAD")]),
    ("Human resources", "HR generalist with talent acquisition, recruitment, onboarding, employee relations, HRIS, payroll and labour relations.", "HR Generalist",
     [("HR Generalist", "Recruitment, onboarding, employee relations and HRIS.", "GOOD"),
      ("Talent Acquisition Specialist", "Hiring, sourcing, interviews and ATS.", "ADJACENT"),
      ("General Manager", "Commercial strategy, sales and operations management.", "BAD"),
      ("Payroll Specialist", "Payroll processing, social security and labour law.", "ADJACENT")]),
    ("Marketing", "Digital marketing specialist with SEO, SEM, Google Analytics, paid search, content strategy, campaign measurement and CRM.", "Digital Marketing Specialist",
     [("Digital Marketing Specialist", "SEO, SEM, paid search, analytics and campaign management.", "GOOD"),
      ("Marketing Analyst", "Marketing analytics, attribution, campaign reporting.", "ADJACENT"),
      ("Data Analyst", "SQL, data modelling and BI dashboards.", "ADJACENT"),
      ("Sales Representative", "Cold calling, prospecting and account management.", "BAD")]),
    ("Supply chain", "Supply chain analyst with inventory planning, procurement, demand forecasting, logistics, SAP, Excel and supplier management.", "Supply Chain Analyst",
     [("Supply Chain Analyst", "Inventory, demand planning, procurement and logistics analytics.", "GOOD"),
      ("Operations Analyst", "Operational KPIs, process optimisation and reporting.", "ADJACENT"),
      ("Financial Analyst", "Financial planning and monthly close.", "ADJACENT"),
      ("Warehouse Supervisor", "Warehouse shifts, forklift operations and dispatch.", "BAD")]),
    ("UX designer", "UX/UI designer. Figma, user research, wireframes, usability testing, interaction design, accessibility and design systems.", "UX Designer",
     [("UX Designer", "User research, wireframes, usability and Figma.", "GOOD"),
      ("Product Designer", "Product discovery, design systems, prototyping and user testing.", "ADJACENT"),
      ("Graphic Designer", "Brand, typography, print and visual identity.", "ADJACENT"),
      ("Product Manager", "Roadmaps, stakeholder management and commercial strategy.", "BAD")]),
    ("Teacher", "Secondary school teacher qualified in mathematics. Lesson planning, classroom management, assessment, curriculum and safeguarding.", "Mathematics Teacher",
     [("Mathematics Teacher", "Teach mathematics, prepare lessons and assess pupils.", "GOOD"),
      ("STEM Tutor", "Tutoring maths and science for secondary students.", "ADJACENT"),
      ("Education Project Manager", "Education programmes, budgets and stakeholder coordination.", "ADJACENT"),
      ("Data Scientist", "Machine learning models and Python.", "BAD")]),
    ("Nursing", "Registered nurse with patient care, medication administration, clinical assessment, emergency care, infection control and hospital ward experience.", "Registered Nurse",
     [("Registered Nurse", "Patient care, clinical assessments and medication administration.", "GOOD"),
      ("Healthcare Assistant", "Personal care, vital signs and patient support.", "ADJACENT"),
      ("Clinical Research Associate", "Clinical trial monitoring, GCP and regulatory files.", "ADJACENT"),
      ("Research Scientist", "Scientific research and data analysis.", "BAD")]),
    ("Customer support", "Customer support specialist with Zendesk, CRM, ticket triage, troubleshooting, SLA management, customer satisfaction and Spanish/English.", "Customer Support Specialist",
     [("Customer Support Specialist", "Zendesk, customer enquiries, troubleshooting and SLAs.", "GOOD"),
      ("Customer Success Manager", "Onboarding, retention, renewals and customer outcomes.", "ADJACENT"),
      ("Sales Development Representative", "Outbound leads, prospecting and sales pipeline.", "ADJACENT"),
      ("Technical Support Engineer", "Troubleshooting technical products and support tickets.", "ADJACENT")]),
    ("Geologist seeking team lead", "Geologist with 10 years in mineral exploration, geological mapping, geochemistry, field operations and project coordination.", "Geology Team Lead",
     [("Geology Team Lead", "Lead geologists, coordinate geological mapping and exploration programmes.", "GOOD"),
      ("Retail Team Leader", "Retail sales, stock, rotas and staff supervision.", "BAD"),
      ("Senior Geologist", "Geology, exploration and resource estimation.", "ADJACENT"),
      ("Project Manager", "Manage cross-functional delivery teams and budgets.", "ADJACENT")]),
    ("Graduate looking for any analyst role", "Recent Economics graduate seeking entry-level analyst work. Degree, statistics, Excel, university research project, no full-time professional experience.", "Junior Analyst",
     [("Junior Business Analyst", "Entry-level requirements analysis, process mapping and stakeholder support.", "GOOD"),
      ("Senior Business Analyst", "Lead complex transformation, manage stakeholders, 7+ years experience.", "BAD"),
      ("Senior Financial Analyst", "Financial planning, budgeting, 5 years experience.", "BAD"),
      ("Data Analyst Intern", "Excel, SQL, reporting and analytics internship.", "ADJACENT")]),
]


def main():
    top1 = 0
    top3 = 0
    seniority_bad = 0
    failures = []
    print(f"{'PROFILE':40} {'EXPECTED':30} {'TOP RESULT':34} {'SCORE':>5} {'RANK':>4}")
    print("-" * 125)
    for name, cv, target, jobs in PROFILES:
        config = {"profile": {"target_title": target, "keywords": {}, "title_signals": []},
                  "search": {"terms": [target]}}
        ranked = []
        for title, desc, label in jobs:
            row = {"title": title, "company": "Synthetic", "description": desc}
            score = score_job(row, config, cv)
            mismatch = professional_domain_mismatch(row, config, cv)
            ranked.append((score, title, label, mismatch))
        ranked.sort(key=lambda x: (-x[0], x[1]))
        relevant_titles = {title for title, desc, label in jobs if label == "GOOD"}
        rank = next((i for i, item in enumerate(ranked, start=1) if item[1] in relevant_titles), 99)
        if rank == 1: top1 += 1
        if rank <= 3: top3 += 1
        top_score, top_title, top_label, top_mismatch = ranked[0]
        print(f"{name[:39]:40} {', '.join(relevant_titles)[:29]:30} {top_title[:33]:34} {top_score:5} {rank:4}")
        if rank != 1:
            failures.append((name, target, rank, ranked))
        if any(label == "BAD" and _seniority_marker(title) for title, desc, label in jobs for _ in [0]):
            pass
    print("-" * 125)
    print(f"Synthetic top-1: {top1}/{len(PROFILES)}")
    print(f"Synthetic top-3: {top3}/{len(PROFILES)}")
    if failures:
        print("\nRANKING FAILURES:")
        for name, target, rank, ranked in failures:
            print(f"\n{name} (target={target}, relevant rank={rank})")
            for score, title, label, mismatch in ranked:
                print(f"  {score:3}  {label:8} {title:35} mismatch={mismatch is not None}")


def _seniority_marker(title: str) -> bool:
    return any(s in title.casefold() for s in ("senior", "lead", "principal", "director"))


if __name__ == "__main__":
    main()
