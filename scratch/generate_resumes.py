import os
from fpdf import FPDF

class PDF(FPDF):
    def header(self):
        self.set_font('helvetica', 'B', 16)
        self.set_text_color(0, 147, 147) # matches theme
        self.cell(0, 10, self.title_name, border=False, ln=True, align='L')
        self.set_font('helvetica', '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, self.subtitle_name, border=False, ln=True, align='L')
        self.ln(5)
        self.line(10, 30, 200, 30)

    def section_header(self, title):
        self.ln(5)
        self.set_font('helvetica', 'B', 12)
        self.set_text_color(0, 147, 147)
        self.cell(0, 8, title, border=False, ln=True, align='L')
        self.ln(2)

    def body_text(self, text):
        self.set_font('helvetica', '', 10)
        self.set_text_color(30, 30, 30)
        self.multi_cell(0, 5, text)
        self.ln(2)

def generate_resume(file_path, name, title, skills, experience):
    pdf = PDF()
    pdf.title_name = name
    pdf.subtitle_name = f"{title} | Email: {name.lower().replace(' ', '')}@email.com | Phone: +1-555-0199"
    pdf.add_page()
    
    # Skills Section
    pdf.section_header("TECHNICAL SKILLS")
    pdf.body_text(", ".join(skills))
    
    # Experience Section
    pdf.section_header("PROFESSIONAL EXPERIENCE")
    for job in experience:
        pdf.set_font('helvetica', 'B', 10)
        pdf.set_text_color(50, 50, 50)
        pdf.cell(0, 5, f"{job['role']} - {job['company']} ({job['dates']})", border=False, ln=True)
        pdf.body_text(job['description'])
        
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    pdf.output(file_path)
    print(f"Generated: {file_path}")

# Generate DevOps Resume
generate_resume(
    "resumes/ENGINEERING/E11_devops.pdf",
    "Alexander Wright",
    "Lead DevOps Engineer",
    ["DevOps", "Docker", "Kubernetes", "AWS EKS", "Terraform", "CI/CD Pipelines", "Jenkins", "Ansible", "Linux", "Python", "Infrastructure as Code", "Kubernetes Clustering"],
    [
        {
            "role": "Senior DevOps Engineer",
            "company": "CloudScale Solutions",
            "dates": "2023 - Present",
            "description": "Architected and managed production Kubernetes clusters on AWS EKS. Created Dockerfiles to containerize microservices, reducing build size by 40%. Automated deployment pipelines using Jenkins CI/CD. Developed infrastructure as code utilizing Terraform and Ansible."
        },
        {
            "role": "System Administrator",
            "company": "TechGrid Corp",
            "dates": "2020 - 2023",
            "description": "Maintained Linux servers, managed Docker containers, and implemented monitoring configurations for high availability software infrastructure."
        }
    ]
)

# Generate Helpdesk Resume
generate_resume(
    "resumes/BPO/B1_helpdesk.pdf",
    "Sarah Jenkins",
    "Customer Support Agent / BPO Specialist",
    ["Helpdesk", "Customer Support", "Call Center Operations", "Ticketing Systems", "Issue Resolution", "Troubleshooting", "Active Listening", "Communication"],
    [
        {
            "role": "Helpdesk Support Representative",
            "company": "ConnectSphere BPO",
            "dates": "2022 - Present",
            "description": "Handled active customer calls at the call center, resolving customer support queries. Managed support tickets in CRM with high precision and fast turnaround. Skilled at active troubleshooting, documentation, and customer issue resolution."
        }
    ]
)
