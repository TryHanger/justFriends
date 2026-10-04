from fastapi import APIRouter

from app.schemas.standards import LifecycleState, QualityReport, StandardInfo
from app.services.project_evidence import build_lifecycle_state
from app.services.quality_checks import run_quality_checks

router = APIRouter()

STANDARDS_DB = [
    StandardInfo(
        designation="ISO/IEC/IEEE 12207",
        organization="ISO/IEC/IEEE",
        title="Software life cycle processes",
        domain="Software Engineering",
        purpose="Defines a comprehensive set of processes for the software lifecycle.",
        example_use="Establishing a framework for software development and maintenance."
    ),
    StandardInfo(
        designation="ISO/IEC 25010",
        organization="ISO/IEC",
        title="Systems and software Quality Requirements and Evaluation (SQuaRE) — System and software quality models",
        domain="Quality Assurance",
        purpose="Defines a quality model with characteristics like functional suitability, performance efficiency, etc.",
        example_use="Defining quality requirements for a new software product."
    ),
    StandardInfo(
        designation="ISO/IEC/IEEE 29148",
        organization="ISO/IEC/IEEE",
        title="Requirements engineering",
        domain="Requirements Engineering",
        purpose="Specifies requirements engineering processes for systems and software.",
        example_use="Creating a Software Requirements Specification (SRS)."
    ),
    StandardInfo(
        designation="ISO/IEC 27001",
        organization="ISO/IEC",
        title="Information security management systems — Requirements",
        domain="Information Security",
        purpose="Provides requirements for an information security management system (ISMS).",
        example_use="Securing user data and API keys in a web application."
    ),
    StandardInfo(
        designation="IEEE 829",
        organization="IEEE",
        title="Standard for Software and System Test Documentation",
        domain="Testing",
        purpose="Specifies the form of a set of documents for use in defined stages of software testing.",
        example_use="Writing test plans and test case specifications."
    ),
    StandardInfo(
        designation="ISO/IEC/IEEE 15288",
        organization="ISO/IEC/IEEE",
        title="System life cycle processes",
        domain="Systems Engineering",
        purpose="Establishes a common framework for describing the life cycle of systems.",
        example_use="Managing the lifecycle of a complex hardware-software system."
    ),
    StandardInfo(
        designation="ISO/IEC/IEEE 42010",
        organization="ISO/IEC/IEEE",
        title="Architecture description",
        domain="Software Architecture",
        purpose="Standardizes conventions for architecture description.",
        example_use="Documenting the architecture of a microservices platform."
    ),
    StandardInfo(
        designation="GOST R ISO/IEC 12207",
        organization="GOST",
        title="Информационная технология. Системная и программная инженерия. Процессы жизненного цикла программных средств",
        domain="Software Engineering",
        purpose="Russian national standard equivalent to ISO/IEC/IEEE 12207.",
        example_use="Compliance in government software projects."
    ),
    StandardInfo(
        designation="GOST R ISO/IEC 25010",
        organization="GOST",
        title="Системная и программная инженерия. Требования и оценка качества систем и программного обеспечения (SQuaRE). Модели качества систем и программных продуктов",
        domain="Quality Assurance",
        purpose="Russian national standard equivalent to ISO/IEC 25010.",
        example_use="Evaluating software quality in domestic projects."
    ),
    StandardInfo(
        designation="GOST 34.601-90",
        organization="GOST",
        title="Автоматизированные системы. Стадии создания",
        domain="Systems Engineering",
        purpose="Defines stages of automated systems creation in Russian standards.",
        example_use="Creating technical assignments for state IT systems."
    )
]

@router.get("/reference", response_model=list[StandardInfo])
def get_standards_reference():
    return STANDARDS_DB

@router.get("/lifecycle", response_model=LifecycleState)
def get_lifecycle_state():
    return build_lifecycle_state()

router.add_api_route("/quality/run", run_quality_checks, methods=["POST"], response_model=QualityReport)
