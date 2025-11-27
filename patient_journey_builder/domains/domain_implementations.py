"""
Domain implementations for the 7 patient journey research domains.
"""

from typing import List, Dict
from .base_domain import BaseDomain, BASE_SYNTHESIS_PROMPT


class EpidemiologyDomain(BaseDomain):
    """Domain 1: Epidemiology research session."""

    domain_id = 1
    domain_name = "Epidemiology"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} prevalence {country} epidemiology",
            "{disease} incidence rate {country} registry",
            "{disease} age distribution gender {country} demographics",
            "{disease} quality of life DLQI {country}",
            "{disease} depression anxiety psychiatric comorbidity",
            "{disease} disease duration remission natural history",
            "{disease} autoimmune comorbidity thyroid disease",
            "{disease} work productivity absenteeism economic burden",
            "{country} population statistics adults",
            "{disease} angioedema prevalence",
            "{disease} sleep disturbance insomnia",
            "{country} population {major_city}",
            "{disease} epidemiology Europe statistics",
            "{disease} patient registry data {country}",
            "{disease} disease burden quality of life",
            "{disease} comorbidities metabolic syndrome",
            "{disease} genetic factors hereditary",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "prevalence_incidence": [
                "Metric", "Value", "95% CI", "Source", "Year", "Confidence"
            ],
            "estimated_patient_population": [
                "Category", "Estimate", "Calculation", "Source"
            ],
            "demographics": [
                "Category", "Value", "Source", "Year"
            ],
            "age_distribution": [
                "Age Group", "Prevalence/%", "Notes", "Source"
            ],
            "comorbidities": [
                "Condition", "Prevalence in Patients", "Relative Risk", "Source"
            ],
            "quality_of_life": [
                "Measure", "Score/Impact", "Comparison", "Source"
            ],
            "disease_characteristics": [
                "Characteristic", "Value", "Notes", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return ["prevalence_incidence", "demographics", "estimated_patient_population"]

    @property
    def critical_fields(self) -> Dict[str, List[str]]:
        return {
            "prevalence_incidence": ["prevalence"],
            "demographics": ["female", "male", "age"],
        }

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: EPIDEMIOLOGY

Focus on extracting:
1. Prevalence and incidence rates with confidence intervals
2. Patient population estimates (diagnosed and undiagnosed)
3. Demographic breakdowns (age, gender, geographic distribution)
4. Comorbidity patterns
5. Quality of life impact measures (DLQI, SF-36, etc.)
6. Disease characteristics (duration, severity, remission rates)

For prevalence/incidence, prioritize:
- National registry data
- Published epidemiological studies
- Government health statistics
"""


class HealthcareFinancesDomain(BaseDomain):
    """Domain 2: Healthcare Finances research session."""

    domain_id = 2
    domain_name = "Healthcare Finances"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} treatment cost {country} healthcare",
            "{disease} economic burden direct costs {country}",
            "{disease} biologic therapy cost reimbursement",
            "{disease} healthcare utilization hospitalization",
            "{country} healthcare system pharmaceutical reimbursement",
            "{disease} cost effectiveness analysis {country}",
            "{disease} indirect costs work productivity",
            "{country} health insurance coverage dermatology",
            "{disease} treatment guidelines {country} recommendations",
            "{disease} drug pricing {country}",
            "TLV {country} reimbursement decisions biologics",
            "{disease} patient out-of-pocket costs",
            "{country} healthcare expenditure dermatological",
            "{disease} budget impact analysis",
            "{disease} specialty pharmacy costs",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "healthcare_costs": [
                "Cost Category", "Annual Cost", "Currency", "Source", "Year"
            ],
            "treatment_costs": [
                "Treatment", "Annual Cost", "Reimbursement Status", "Source"
            ],
            "healthcare_utilization": [
                "Service Type", "Annual Visits/Episodes", "Cost per Visit", "Source"
            ],
            "reimbursement_landscape": [
                "Treatment", "Reimbursement Status", "Restrictions", "Source"
            ],
            "economic_burden": [
                "Category", "Cost/Impact", "Notes", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return ["healthcare_costs", "treatment_costs", "reimbursement_landscape"]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: HEALTHCARE FINANCES

Focus on extracting:
1. Direct medical costs (consultations, treatments, hospitalizations)
2. Treatment costs by therapy type
3. Reimbursement status of key treatments
4. Healthcare resource utilization patterns
5. Indirect costs (productivity loss, absenteeism)
6. Out-of-pocket patient expenses

Note the currency for all cost data. Convert to local currency where possible.
"""


class CompetitiveLandscapeDomain(BaseDomain):
    """Domain 3: Competitive Landscape research session."""

    domain_id = 3
    domain_name = "Competitive Landscape"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} treatment market share {country}",
            "{disease} biologic therapy market {country}",
            "{disease} approved treatments {country}",
            "{disease} pipeline drugs clinical trials",
            "{disease} omalizumab market share",
            "{disease} JAK inhibitors market",
            "{disease} treatment guidelines recommendations",
            "{disease} emerging therapies development",
            "{disease} biosimilars market entry",
            "{disease} competitive analysis pharma",
            "{disease} market forecast {country}",
            "EMA approved {disease} treatments",
            "{disease} prescription trends {country}",
            "{disease} market access barriers",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "approved_treatments": [
                "Drug Name", "Company", "Mechanism", "Approval Date", "Indication"
            ],
            "market_share": [
                "Treatment", "Market Share %", "Revenue", "Year", "Source"
            ],
            "pipeline_drugs": [
                "Drug Name", "Company", "Phase", "Mechanism", "Expected Approval"
            ],
            "treatment_positioning": [
                "Treatment Line", "Recommended Treatments", "Guidelines Source"
            ],
            "competitive_dynamics": [
                "Factor", "Current State", "Trend", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return ["approved_treatments", "market_share", "pipeline_drugs"]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: COMPETITIVE LANDSCAPE

Focus on extracting:
1. Currently approved treatments with approval dates
2. Market share data by treatment
3. Pipeline drugs and development stages
4. Treatment guidelines and positioning
5. Key market trends and dynamics
6. Biosimilar/generic competition

Include both approved and pipeline products. Note mechanism of action for all drugs.
"""


class ClinicalPathwaysDomain(BaseDomain):
    """Domain 4: Clinical Pathways research session."""

    domain_id = 4
    domain_name = "Clinical Pathways"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} treatment algorithm {country}",
            "{disease} clinical guidelines {country} dermatology",
            "{disease} diagnosis criteria",
            "{disease} referral pathway specialist",
            "{disease} first line second line treatment",
            "{disease} biologic eligibility criteria",
            "{disease} treatment escalation guidelines",
            "{disease} disease activity scoring",
            "{disease} treatment response criteria",
            "{disease} primary care management",
            "{disease} specialist referral patterns",
            "{disease} treatment duration guidelines",
            "{disease} switching therapy guidelines",
            "EAACI guidelines {disease}",
            "{disease} step therapy protocol",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "treatment_algorithm": [
                "Step", "Treatment", "Duration", "Response Criteria", "Source"
            ],
            "diagnostic_pathway": [
                "Stage", "Assessment", "Criteria", "Referral Trigger"
            ],
            "treatment_lines": [
                "Line", "Treatments", "Duration", "Response Rate", "Source"
            ],
            "referral_patterns": [
                "From", "To", "Trigger", "Typical Wait Time", "Source"
            ],
            "response_criteria": [
                "Measure", "Definition", "Target", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return ["treatment_algorithm", "treatment_lines"]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: CLINICAL PATHWAYS

Focus on extracting:
1. Step-by-step treatment algorithms
2. First-line, second-line, third-line treatments
3. Diagnostic and assessment criteria
4. Referral patterns between care settings
5. Treatment duration and response criteria
6. Eligibility criteria for advanced therapies

Reference specific clinical guidelines (national and international).
"""


class PatientExperienceDomain(BaseDomain):
    """Domain 5: Patient Experience research session."""

    domain_id = 5
    domain_name = "Patient Experience"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} patient experience quality of life",
            "{disease} patient survey satisfaction {country}",
            "{disease} patient journey barriers",
            "{disease} patient support programs {country}",
            "{disease} patient associations {country}",
            "{disease} patient unmet needs",
            "{disease} treatment adherence barriers",
            "{disease} patient education resources",
            "{disease} diagnosis delay patient",
            "{disease} emotional impact patients",
            "{disease} patient preference treatment",
            "{disease} caregiver burden",
            "{disease} patient advocacy groups {country}",
            "{disease} shared decision making",
            "{disease} patient reported outcomes",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "patient_journey_map": [
                "Stage", "Experience", "Pain Points", "Duration", "Source"
            ],
            "unmet_needs": [
                "Need Category", "Description", "Impact", "Source"
            ],
            "patient_support": [
                "Program/Resource", "Provider", "Services", "Access"
            ],
            "treatment_preferences": [
                "Factor", "Patient Priority", "Evidence", "Source"
            ],
            "barriers_to_care": [
                "Barrier", "Impact", "Affected Population", "Source"
            ],
            "patient_organizations": [
                "Organization", "Focus", "Services", "Website"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return ["patient_journey_map", "unmet_needs", "barriers_to_care"]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: PATIENT EXPERIENCE

Focus on extracting:
1. Patient journey from symptoms to treatment
2. Key pain points and barriers to care
3. Unmet medical and non-medical needs
4. Patient support programs and resources
5. Treatment preferences and priorities
6. Patient organizations and advocacy groups

Include patient voice/quotes where available from surveys or studies.
"""


class SegmentationDomain(BaseDomain):
    """Domain 6: Patient Segmentation research session."""

    domain_id = 6
    domain_name = "Patient Segmentation"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} patient segmentation phenotypes",
            "{disease} severity classification mild moderate severe",
            "{disease} patient subgroups characteristics",
            "{disease} treatment responders non-responders",
            "{disease} biomarkers patient selection",
            "{disease} disease subtypes classification",
            "{disease} refractory patients definition",
            "{disease} special populations elderly pediatric",
            "{disease} comorbidity clusters",
            "{disease} treatment-naive experienced",
            "{disease} chronic acute classification",
            "{disease} patient profiles personas",
            "{disease} precision medicine biomarkers",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "patient_segments": [
                "Segment", "Characteristics", "Size %", "Treatment Approach", "Source"
            ],
            "severity_distribution": [
                "Severity Level", "Definition", "Prevalence %", "Source"
            ],
            "phenotypes": [
                "Phenotype", "Characteristics", "Prevalence", "Treatment Response", "Source"
            ],
            "special_populations": [
                "Population", "Considerations", "Size", "Treatment Modifications"
            ],
            "biomarkers": [
                "Biomarker", "Use", "Predictive Value", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return ["patient_segments", "severity_distribution"]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: PATIENT SEGMENTATION

Focus on extracting:
1. Patient segments by severity, phenotype, or characteristics
2. Severity distribution (mild, moderate, severe)
3. Treatment response profiles
4. Special populations (elderly, pediatric, pregnant)
5. Biomarkers for patient selection
6. Refractory/difficult-to-treat patient definitions

Quantify segment sizes where possible (% of total population).
"""


class StakeholdersDomain(BaseDomain):
    """Domain 7: Stakeholder Mapping research session."""

    domain_id = 7
    domain_name = "Stakeholder Mapping"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} key opinion leaders {country}",
            "{disease} dermatology specialists {country}",
            "{disease} treatment centers excellence {country}",
            "{disease} clinical research sites {country}",
            "{disease} payer decision makers {country}",
            "{disease} health technology assessment {country}",
            "{disease} patient advocacy leaders {country}",
            "{country} dermatology society association",
            "{disease} medical education programs {country}",
            "{disease} healthcare policy {country}",
            "{disease} market access stakeholders",
            "{country} pharmaceutical pricing committee",
            "{disease} guideline authors {country}",
            "{disease} registry researchers {country}",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "key_opinion_leaders": [
                "Name", "Institution", "Role/Expertise", "Influence Area"
            ],
            "treatment_centers": [
                "Center Name", "Location", "Specialization", "Patient Volume"
            ],
            "payer_stakeholders": [
                "Organization", "Role", "Decision Power", "Key Contacts"
            ],
            "professional_societies": [
                "Organization", "Focus", "Key Activities", "Website"
            ],
            "patient_organizations": [
                "Organization", "Focus", "Membership", "Key Activities"
            ],
            "regulatory_bodies": [
                "Body", "Role", "Key Decisions", "Contact"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return ["key_opinion_leaders", "treatment_centers", "payer_stakeholders"]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: STAKEHOLDER MAPPING

Focus on extracting:
1. Key opinion leaders in the disease area
2. Major treatment centers and their expertise
3. Payer and reimbursement decision makers
4. Professional societies and their influence
5. Patient organizations and advocates
6. Regulatory and HTA bodies

Include names and institutions where publicly available. Note influence level.
"""


# Domain registry for easy access
DOMAINS = {
    1: EpidemiologyDomain(),
    2: HealthcareFinancesDomain(),
    3: CompetitiveLandscapeDomain(),
    4: ClinicalPathwaysDomain(),
    5: PatientExperienceDomain(),
    6: SegmentationDomain(),
    7: StakeholdersDomain(),
}


def get_domain(domain_id: int) -> BaseDomain:
    """
    Get a domain instance by ID.

    Args:
        domain_id: Domain number (1-7)

    Returns:
        Domain instance

    Raises:
        ValueError: If domain_id is invalid
    """
    if domain_id not in DOMAINS:
        raise ValueError(f"Invalid domain ID: {domain_id}. Must be 1-7.")
    return DOMAINS[domain_id]


def get_all_domains() -> Dict[int, BaseDomain]:
    """
    Get all domain instances.

    Returns:
        Dictionary mapping domain ID to domain instance
    """
    return DOMAINS.copy()
