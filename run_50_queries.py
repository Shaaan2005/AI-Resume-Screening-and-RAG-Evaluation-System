"""Run 50 diverse queries through detect_category() to check department detection."""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import detect_category, _CAT_DESCRIPTIONS
from chroma_search import get_cross_encoder

# 50 Distinct, Diverse Search Queries across all 24 departments
QUERIES = [
    # 1-10: Software, IT, Data & Tech
    "select 5 preeminent engineering candidate",                  # 1. Engineering (classic test)
    "looking for a C++ developer with multithreading experience", # 2. C++ / Low-level
    "need a devops engineer skilled in docker and kubernetes",    # 3. Cloud / Infra
    "frontend developer proficient in React and TypeScript",     # 4. Web Dev
    "system administrator with Linux and Active Directory",      # 5. IT / Sysadmin
    "cybersecurity analyst for network vulnerability assessment", # 6. Security
    "data engineer experienced in PySpark and ETL pipelines",     # 7. Data
    "iOS mobile app developer using Swift and SwiftUI",           # 8. Mobile Dev
    "full stack programmer with Node.js and MongoDB",            # 9. Full Stack
    "AI engineer specializing in deep learning and PyTorch",      # 10. AI / ML

    # 11-20: Design, Media & Public Relations
    "UI/UX designer skilled in Figma and user research",         # 11. Designer
    "graphic designer for branding and vector illustrations",      # 12. Visual Art
    "digital marketing expert for SEO and Google Ads campaigns",  # 13. Digital Media
    "social media manager for content creation and video editing",# 14. Social Media
    "public relations officer for press release and media relations", # 15. PR
    "creative direction lead for visual advertising",             # 16. Visual Direction
    "animator for 3D motion graphics and Maya",                   # 17. Animation
    "copywriter for technical documentation and blog posts",      # 18. Content
    "photographer for commercial product photo shoots",           # 19. Photography
    "web designer specializing in responsive CSS layouts",        # 20. Web Design

    # 21-30: Finance, Banking & Accounting
    "chartered accountant for tax audit and GST filing",          # 21. Accountant
    "financial analyst for valuation and financial modeling",     # 22. Finance
    "investment banker for merger and acquisition strategy",      # 23. Banking
    "credit analyst for corporate loan underwriting",             # 24. Credit / Banking
    "payroll specialist proficient in Tally and QuickBooks",      # 25. Payroll / Accounting
    "treasury manager for liquidity and cash flow management",    # 26. Treasury
    "portfolio manager for equity research and wealth management",# 27. Wealth
    "forensic auditor for financial fraud investigation",         # 28. Audit
    "risk manager for Anti-Money Laundering regulatory compliance",# 29. Risk / Banking
    "bookkeeper experienced in GAAP financial reporting",          # 30. Bookkeeping

    # 31-40: Healthcare, Education & Services
    "ICU nurse with emergency patient care experience",            # 31. Healthcare / Nursing
    "pediatric surgeon for clinical treatment and diagnosis",     # 32. Doctor / Surgery
    "pharmacist for medication administration and prescription",  # 33. Pharmacy
    "high school physics teacher for curriculum development",      # 34. Education
    "university professor for academic research and lecturing",   # 35. Professor
    "head chef experienced in fine dining and menu planning",      # 36. Culinary / Chef
    "pastry chef specialized in baking and recipe formulation",   # 37. Baker / Chef
    "personal trainer for strength training and weight loss",     # 38. Fitness
    "yoga instructor for wellness and mindfulness coaching",      # 39. Fitness / Yoga
    "helpdesk support agent for customer issue resolution",        # 40. BPO / Customer Service

    # 41-50: Trade, Legal, Operations & Industry
    "litigation lawyer for corporate contract drafting",           # 41. Legal / Advocate
    "civil site engineer for concrete construction supervision",   # 42. Construction
    "farm manager skilled in crop management and soil irrigation", # 43. Agriculture
    "automotive mechanic for electric vehicle engine diagnostics",# 44. Automobile
    "airline pilot with flight operation and navigation license", # 45. Aviation
    "flight attendant for cabin crew safety management",          # 46. Aviation / Crew
    "garment merchandiser for fashion textile quality control",    # 47. Apparel
    "sales executive skilled in cold calling and lead generation", # 48. Sales
    "talent acquisition recruiter for HR onboarding",             # 49. HR
    "management consultant for digital transformation strategy",  # 50. Consulting
]

print("=" * 100)
print(f"{'#':<4} {'QUERY':<65} {'DETECTED DEPARTMENT':<25}")
print("=" * 100)

for i, query in enumerate(QUERIES, 1):
    dept = detect_category(query)
    dept_str = dept if dept else "NONE (Search All)"
    print(f"{i:<4} {query:<65} {dept_str:<25}")

print("=" * 100)
print(f"\nCompleted testing {len(QUERIES)} queries successfully!")
