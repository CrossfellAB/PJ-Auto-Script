"""
Enhanced domain implementations for the 7 patient journey research domains.

Each domain now includes:
- 17-20 search queries (up from 13-17)
- 12-17 table schemas (up from 5-7)
- Detailed synthesis prompts requiring named entities, confidence levels, and data gaps
"""

from typing import List, Dict
from .base_domain import BaseDomain, BASE_SYNTHESIS_PROMPT


class EpidemiologyDomain(BaseDomain):
    """Domain 1: Epidemiology research session - Enhanced."""

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
            "{disease} mortality morbidity healthcare utilization",
            "{disease} regional distribution {country}",
            "{disease} diagnostic pathway primary care specialist",
            "{disease} trend data prevalence over time",
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
            "prevalence_validation": [
                "Source", "Prevalence", "Notes"
            ],
            "demographics": [
                "Category", "Value", "Source", "Year"
            ],
            "age_distribution": [
                "Age Group", "Prevalence/%", "Notes", "Source"
            ],
            "gender_age_interaction": [
                "Finding", "Value", "Source"
            ],
            "regional_distribution": [
                "Region", "Population", "Prevalence", "Est. Cases", "Data Quality", "Source"
            ],
            "mortality_morbidity": [
                "Metric", "Value", "Comparator", "Source", "Year"
            ],
            "healthcare_utilization": [
                "Metric", "Value", "Timeframe", "Source"
            ],
            "quality_of_life": [
                "Metric", "Value", "Interpretation", "Source"
            ],
            "psychiatric_comorbidity": [
                "Comorbidity", "Prevalence", "vs. General Pop", "Source"
            ],
            "physical_comorbidities": [
                "Comorbidity", "Prevalence", "Source"
            ],
            "disease_natural_history": [
                "Metric", "Value", "Source"
            ],
            "prognostic_factors": [
                "Factor", "Impact on Duration/Severity", "Source"
            ],
            "diagnostic_pathway": [
                "Metric", "Value", "Source"
            ],
            "treatment_landscape_overview": [
                "Metric", "Value", "Source"
            ],
            "work_productivity_impact": [
                "Metric", "Value", "Source"
            ],
            "patient_journey_flow": [
                "Journey Step", "Est. Patients", "% of Total", "Drop-out %", "Source"
            ],
            "trend_data": [
                "Year", "Prevalence", "Incidence", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return [
            "prevalence_incidence", "demographics", "estimated_patient_population",
            "regional_distribution", "quality_of_life", "psychiatric_comorbidity",
            "disease_natural_history", "diagnostic_pathway"
        ]

    @property
    def critical_fields(self) -> Dict[str, List[str]]:
        return {
            "prevalence_incidence": ["prevalence", "incidence"],
            "demographics": ["female", "male", "age"],
            "estimated_patient_population": ["total", "diagnosed"],
        }

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: EPIDEMIOLOGY

### COMPREHENSIVE DATA REQUIREMENTS
You must extract data for ALL of the following categories:

1. **Prevalence & Incidence**
   - Point prevalence with 95% CI
   - Period prevalence
   - Annual incidence rate
   - Prevalence per 100,000 population
   - Cross-validate with 2+ sources

2. **Patient Population Estimates**
   - Total national population
   - Adult population
   - Estimated total patients (from prevalence)
   - Diagnosed vs undiagnosed estimates
   - Annual new cases

3. **Demographics**
   - Female/Male percentage and ratio
   - Mean/median age at diagnosis
   - Age distribution by decade (0-17, 18-29, 30-39, etc.)
   - Gender-age interactions

4. **Regional Distribution**
   - Major regions/counties with population
   - Regional prevalence estimates
   - Urban vs rural (if available)

5. **Mortality & Morbidity**
   - All-cause mortality hazard ratio
   - Disease-specific mortality
   - Healthcare utilization (ED visits, hospitalizations, outpatient visits)

6. **Quality of Life**
   - DLQI scores
   - EQ-5D scores
   - Disease-specific QoL measures
   - % with severe QoL impact

7. **Psychiatric Comorbidity**
   - Depression prevalence (diagnosed and screening)
   - Anxiety prevalence
   - Sleep disorders
   - Suicidal ideation risk

8. **Physical Comorbidities**
   - Autoimmune conditions (thyroid, etc.)
   - Atopic conditions (asthma, rhinitis, etc.)
   - Cardiovascular disease
   - Metabolic conditions

9. **Disease Natural History**
   - Mean/median disease duration
   - Remission rates at 1, 2, 5, 10 years
   - Relapsing-remitting course percentage
   - Prognostic factors

10. **Diagnostic Pathway**
    - Mean/median diagnostic delay
    - % diagnosed in primary care vs specialist
    - First provider seen

11. **Treatment Landscape Overview**
    - % on any treatment
    - % on first-line, second-line, biologic therapy
    - % with uncontrolled disease

12. **Work & Productivity Impact**
    - Work absenteeism %
    - Presenteeism %
    - Overall work impairment
    - Annual productivity loss (if available)

13. **Patient Journey Flow**
    - Estimated patients at each journey step
    - Drop-out percentage at each transition
    - From symptom onset → diagnosis → treatment → outcomes

14. **Trend Data**
    - Year-over-year prevalence/incidence trends
    - Projected future trends

### PRIORITY SOURCES FOR {country}
- National patient registries
- Published epidemiological studies from {country}
- Government health statistics
- European benchmark data for validation
"""


class HealthcareFinancesDomain(BaseDomain):
    """Domain 2: Healthcare Finances research session - Enhanced."""

    domain_id = 2
    domain_name = "Healthcare Finances"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} treatment cost {country} healthcare",
            "{disease} omalizumab Xolair price {country} reimbursement",
            "{country} drug price antihistamine pharmaceutical",
            "{disease} economic burden Europe direct costs",
            "{country} healthcare out-of-pocket cost patient",
            "{country} dermatologist specialist per capita",
            "{country} wait times specialist dermatology",
            "{country} healthcare payer structure regions",
            "{country} drug reimbursement decision {disease}",
            "{country} private health insurance prevalence",
            "{disease} healthcare cost per patient Europe",
            "{disease} biologic reimbursement {country}",
            "{country} healthcare regional variation budget",
            "{disease} productivity costs absenteeism",
            "{disease} dupilumab Dupixent price {country}",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "drug_pricing_branded": [
                "Treatment", "Generic Name", "Company", "List Price", "Net Price (est.)", "Currency", "Per Unit", "Annual Cost", "Source"
            ],
            "drug_pricing_generic_biosimilar": [
                "Treatment", "Generic Name", "List Price", "Currency", "Per Unit", "Annual Cost", "Source"
            ],
            "price_comparison_international": [
                "Treatment", "Country Price", "EU Average", "US Price", "Source"
            ],
            "reimbursement_status": [
                "Treatment", "Reimbursement Status", "Coverage Level", "Restrictions", "Effective Date", "Source"
            ],
            "reimbursement_criteria": [
                "Treatment", "Required Criteria", "Documentation Needed", "Source"
            ],
            "patient_cost_sharing": [
                "Cost Type", "Amount", "Currency", "Cap/Maximum", "Source"
            ],
            "patient_financial_burden": [
                "Metric", "Value", "Source"
            ],
            "condition_specific_spending": [
                "Category", "Annual Amount", "Currency", "% of Total", "Source", "Year"
            ],
            "per_patient_costs": [
                "Category", "Mean Cost", "Median Cost", "Range", "Currency", "Source"
            ],
            "payer_structure": [
                "Payer Type", "Name", "Role", "Coverage Scope", "Decision Authority", "Source"
            ],
            "key_payer_bodies": [
                "Body", "Full Name", "Role in Disease", "Key Decisions", "Source"
            ],
            "access_requirements": [
                "Requirement", "Details", "Applies To", "Enforcement", "Source"
            ],
            "step_therapy_protocol": [
                "Step", "Treatment", "Duration Required", "Failure Criteria", "Source"
            ],
            "healthcare_staffing": [
                "Specialty", "Total Number", "Per 100,000 Pop", "Ratio to Patients", "Source"
            ],
            "healthcare_facilities": [
                "Facility Type", "Number", "Distribution", "Source"
            ],
            "wait_times": [
                "Stage", "Median Wait", "Range", "Guarantee (if any)", "Source"
            ],
            "regional_budget_variation": [
                "Region", "Healthcare Budget", "Per Capita", "Source"
            ],
            "private_healthcare": [
                "Aspect", "Public System", "Private System", "Source"
            ],
            "economic_burden_summary": [
                "Burden Type", "Annual Value", "Currency", "% of Total", "Source"
            ],
            "productivity_impact": [
                "Metric", "Value", "Annual Cost (est.)", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return [
            "drug_pricing_branded", "reimbursement_status", "patient_cost_sharing",
            "payer_structure", "per_patient_costs", "wait_times"
        ]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: HEALTHCARE FINANCES

### COMPREHENSIVE DATA REQUIREMENTS

1. **Drug Pricing**
   - Branded treatment prices (list price, estimated net price)
   - Generic/biosimilar prices
   - International price comparison (vs EU average, vs US)
   - Annual treatment costs per therapy

2. **Reimbursement Status**
   - Each treatment's reimbursement status
   - Coverage level (full, partial, restricted)
   - Specific restrictions/criteria
   - Effective dates of decisions

3. **Reimbursement Criteria**
   - Prior authorization requirements
   - Step therapy requirements
   - Documentation needed
   - Specialist initiation requirements

4. **Patient Cost-Sharing**
   - Prescription co-pay structure
   - Specialist visit co-pay
   - Annual out-of-pocket caps
   - Hospital stay daily rates

5. **Healthcare Expenditure**
   - Total condition-specific spending
   - Breakdown by category (drugs, outpatient, inpatient, emergency)
   - Per-patient costs by severity

6. **Payer Structure**
   - National payer bodies and roles
   - Regional payer structure
   - HTA body role and recent decisions
   - Drug committee structure

7. **Access Requirements**
   - Prior authorization requirements
   - Step therapy protocols
   - Treatment failure documentation
   - Periodic reassessment requirements

8. **Healthcare Resources**
   - Specialist availability (dermatologists, allergists)
   - Facility numbers (clinics, hospitals)
   - Regional distribution

9. **Wait Times**
   - GP to specialist referral time
   - Treatment approval time
   - Regional variation

10. **Private Healthcare**
    - Private insurance prevalence
    - Private vs public wait times
    - Cost comparison

11. **Economic Burden**
    - Direct medical costs
    - Direct non-medical costs
    - Indirect costs (productivity loss)
    - Total economic burden per patient

### CURRENCY NOTE
All costs should be in local currency ({country}) with year noted.
Include conversion context where relevant.
"""


class CompetitiveLandscapeDomain(BaseDomain):
    """Domain 3: Competitive Landscape research session - Enhanced."""

    domain_id = 3
    domain_name = "Competitive Landscape"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} approved treatments {country} EMA",
            "{disease} treatment guidelines {country} Europe EAACI",
            "{disease} omalizumab Xolair {country} reimbursement",
            "{disease} remibrutinib phase 3 approval EMA",
            "{disease} barzolvolimab phase 3 clinical trials",
            "{disease} market size {country} Nordic",
            "{disease} omalizumab biosimilar EMA approval",
            "antihistamine cetirizine loratadine {disease} treatment first line",
            "Novartis Sanofi Regeneron {disease} dermatology market {country}",
            "cyclosporin {disease} third line treatment immunosuppressant",
            "{disease} rilzabrutinib phase 2 clinical trial",
            "{disease} omalizumab response rate efficacy UAS7",
            "{disease} dupilumab approval EMA",
            "{disease} pipeline drugs development 2024 2025",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "first_line_treatments": [
                "Treatment", "Generic Name", "Company", "Mechanism", "Approval Date", "Indication", "Source"
            ],
            "second_line_treatments": [
                "Treatment", "Generic Name", "Company", "Mechanism", "Approval Date", "Indication", "Source"
            ],
            "third_line_treatments": [
                "Treatment", "Generic Name", "Company", "Mechanism", "Approval Date", "Indication", "Source"
            ],
            "generics_biosimilars": [
                "Treatment", "Reference Product", "Company", "Approval Date", "Price vs Original", "Source"
            ],
            "treatment_guidelines": [
                "Guideline", "Publisher", "Year", "Adoption in Country", "Source"
            ],
            "treatment_algorithm": [
                "Line", "Treatment(s)", "Criteria to Advance", "Duration", "Source"
            ],
            "guideline_recommendations": [
                "Recommendation", "Strength", "Evidence Level", "Source"
            ],
            "country_specific_adaptations": [
                "Guideline Element", "International Standard", "Country Adaptation", "Source"
            ],
            "market_share": [
                "Treatment", "Market Share %", "Trend", "Patient Volume", "Source"
            ],
            "market_size": [
                "Metric", "Value", "Currency", "Year", "Source"
            ],
            "pipeline_phase_3": [
                "Compound", "Company", "Mechanism", "Target Indication", "Expected Approval", "Differentiation", "Source"
            ],
            "pipeline_phase_2": [
                "Compound", "Company", "Mechanism", "Target Indication", "Phase 2 Completion", "Source"
            ],
            "pipeline_discontinued": [
                "Compound", "Company", "Phase", "Reason for Discontinuation", "Source"
            ],
            "patent_expirations": [
                "Treatment", "Patent Holder", "Patent Expiry", "Biosimilar/Generic Expected", "Source"
            ],
            "competitor_company_profiles": [
                "Company", "Products in Disease", "Market Position", "Pipeline", "Key Activities", "Source"
            ],
            "competitor_activity": [
                "Company", "Treatment", "Activity Type", "Details", "Date", "Source"
            ],
            "efficacy_comparison": [
                "Treatment", "Primary Endpoint", "Response Rate", "vs Placebo", "NNT", "Source"
            ],
            "safety_comparison": [
                "Treatment", "Key Safety Concerns", "Black Box Warning", "Monitoring Required", "Source"
            ],
            "treatment_positioning": [
                "Treatment", "Positioning", "Target Patient", "Competitive Advantage", "Vulnerability", "Source"
            ],
            "unmet_needs": [
                "Unmet Need", "Current Gap", "Potential Solution", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return [
            "first_line_treatments", "second_line_treatments", "treatment_algorithm",
            "market_share", "pipeline_phase_3", "efficacy_comparison", "treatment_positioning"
        ]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: COMPETITIVE LANDSCAPE

### COMPREHENSIVE DATA REQUIREMENTS

1. **Approved Treatments**
   - First-line treatments (antihistamines)
   - Second-line treatments (biologics)
   - Third-line/advanced treatments
   - Generics and biosimilars

2. **Treatment Guidelines**
   - Primary guideline (EAACI, national, etc.)
   - Treatment algorithm with line-by-line detail
   - Strength of recommendations
   - Country-specific adaptations

3. **Market Data**
   - Market share by treatment
   - Market size (global, regional, country)
   - Growth trends and forecasts

4. **Pipeline Analysis**
   - Phase 3 compounds with expected approval dates
   - Phase 2 compounds
   - Recently discontinued compounds and reasons
   - Differentiation from current treatments

5. **Patent Expirations**
   - Key patent expiry dates
   - Expected biosimilar/generic entry

6. **Competitor Profiles**
   - Major companies in the space
   - Their products and pipeline
   - Recent activities (approvals, publications, submissions)

7. **Efficacy Comparison**
   - Head-to-head data where available
   - Response rates by treatment
   - Primary endpoints and NNT

8. **Safety Comparison**
   - Key safety concerns per treatment
   - Monitoring requirements
   - Black box warnings

9. **Treatment Positioning**
   - Each treatment's positioning
   - Target patient population
   - Competitive advantages and vulnerabilities

10. **Unmet Needs**
    - Current gaps in treatment landscape
    - Potential solutions from pipeline

### KEY PIPELINE COMPOUNDS TO TRACK
- Remibrutinib (Novartis) - BTK inhibitor
- Barzolvolimab (Celldex) - anti-KIT
- Rilzabrutinib (Sanofi) - BTK inhibitor
- Dupilumab (Sanofi/Regeneron) - anti-IL-4/IL-13
- Omalizumab biosimilars
"""


class ClinicalPathwaysDomain(BaseDomain):
    """Domain 4: Clinical Pathways research session - Enhanced."""

    domain_id = 4
    domain_name = "Clinical Pathways"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{country} healthcare system structure primary secondary tertiary care",
            "{country} dermatology specialist services structure",
            "{disease} referral criteria {country} primary care specialist",
            "{country} healthcare guarantee waiting time specialist",
            "{disease} diagnostic criteria tests laboratory workup",
            "{disease} activity score UAS7 UCT assessment tool monitoring",
            "{country} electronic health records EHR system",
            "{country} patient portal telemedicine digital health",
            "{disease} biologic prescribing specialist initiation {country}",
            "{country} private healthcare dermatology access",
            "{country} regional healthcare variation dermatology access",
            "university hospitals {country} dermatology specialist center excellence",
            "{disease} treatment algorithm step therapy protocol",
            "{disease} monitoring outcomes follow-up",
            "EAACI guidelines {disease} treatment algorithm",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "healthcare_system_structure": [
                "Level", "Description", "Typical Facilities", "Role in Disease", "Source"
            ],
            "key_healthcare_settings": [
                "Setting Type", "Name/Description", "Number", "Geographic Distribution", "Source"
            ],
            "referral_pathways": [
                "From", "To", "Criteria", "Typical Wait", "Bottleneck?", "Source"
            ],
            "referral_requirements": [
                "Pathway", "Referral Type", "Documentation Required", "Validity Period", "Source"
            ],
            "specialist_access_routes": [
                "Route", "Requirements", "Wait Time", "Cost to Patient", "Source"
            ],
            "diagnostic_criteria": [
                "Criterion", "Requirement", "Source"
            ],
            "recommended_workup": [
                "Test/Assessment", "When Required", "Purpose", "Source"
            ],
            "scoring_assessment_tools": [
                "Tool", "Full Name", "Use", "Frequency", "Source"
            ],
            "disease_control_definitions": [
                "Category", "UAS7 Range", "UCT Range", "Clinical Definition", "Source"
            ],
            "treatment_algorithm": [
                "Step", "Treatment", "Duration", "Response Criteria", "Source"
            ],
            "monitoring_follow_up": [
                "Stage", "Monitoring Type", "Frequency", "Purpose", "Source"
            ],
            "digital_health_tools": [
                "Tool/Platform", "Provider", "Function", "Adoption", "Source"
            ],
            "ehr_systems": [
                "System", "Coverage", "Disease-Specific Features", "Source"
            ],
            "telemedicine_options": [
                "Provider", "Services", "Coverage", "Patient Cost", "Source"
            ],
            "specialist_prescribing_requirements": [
                "Treatment", "Prescriber Level", "Initiation Requirements", "Monitoring", "Source"
            ],
            "centers_of_excellence": [
                "Center", "Location", "Specialization", "Research Activity", "Source"
            ],
            "regional_variation": [
                "Region", "Access Level", "Wait Times", "Notes", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return [
            "healthcare_system_structure", "referral_pathways", "diagnostic_criteria",
            "treatment_algorithm", "specialist_prescribing_requirements"
        ]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: CLINICAL PATHWAYS

### COMPREHENSIVE DATA REQUIREMENTS

1. **Healthcare System Structure**
   - Care levels (primary, secondary, tertiary, quaternary)
   - Typical facilities at each level
   - Role in disease management

2. **Key Healthcare Settings**
   - Primary care clinics/health centers
   - General hospitals
   - University hospitals
   - Specialist clinics (public and private)

3. **Referral Pathways**
   - Standard referral flow
   - Requirements and documentation
   - Typical wait times
   - Bottlenecks in the system

4. **Diagnostic Requirements**
   - Diagnostic criteria
   - Recommended workup (lab tests, assessments)
   - When to refer for specialist assessment

5. **Scoring & Assessment Tools**
   - UAS7 (Urticaria Activity Score)
   - UCT (Urticaria Control Test)
   - Disease control definitions
   - Monitoring frequency

6. **Treatment Algorithm**
   - Step-by-step treatment pathway
   - First-line, second-line, third-line
   - Criteria to advance to next line
   - Duration at each step

7. **Digital Health Tools**
   - EHR systems in use
   - Patient portals
   - Telemedicine platforms
   - Disease-specific apps

8. **Specialist Requirements**
   - Who can prescribe biologics
   - Initiation requirements
   - Monitoring requirements

9. **Centers of Excellence**
   - Named centers/hospitals with expertise
   - Research activity
   - Patient volume estimates

10. **Regional Variation**
    - Access differences across regions
    - Wait time variation
    - Resource distribution

### COUNTRY-SPECIFIC FOCUS
Map the actual healthcare system of {country}:
- Name specific EHR systems
- Name specific hospital networks
- Reference actual patient portals
- Include healthcare guarantee timeframes
"""


class PatientExperienceDomain(BaseDomain):
    """Domain 5: Patient Experience research session - Enhanced."""

    domain_id = 5
    domain_name = "Patient Experience"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} patient experience quality of life",
            "{disease} patient journey stages diagnosis treatment",
            "{disease} diagnostic delay patient pathway",
            "{disease} patient unmet needs survey",
            "{disease} patient satisfaction treatment",
            "{disease} emotional impact psychological burden",
            "{disease} stigmatization patients",
            "{disease} sleep disturbance patient impact",
            "{disease} work impact patient productivity",
            "{disease} patient beliefs misconceptions",
            "{disease} treatment adherence barriers",
            "{disease} patient support resources {country}",
            "{disease} patient organization {country} allergy",
            "{disease} patient quotes experiences",
            "{disease} cultural factors patient {country}",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "patient_journey_stages": [
                "Stage", "Description", "Duration", "Key Activities", "Source"
            ],
            "journey_pain_points": [
                "Stage", "Pain Point", "Impact", "Frequency", "Source"
            ],
            "emotional_journey": [
                "Journey Step", "Positive Feelings", "Negative Feelings", "Predominant Emotion", "Source"
            ],
            "patient_quotes": [
                "Quote", "Context", "Source", "Year"
            ],
            "diagnostic_delay_factors": [
                "Factor", "Impact on Delay", "Evidence", "Source"
            ],
            "information_sources": [
                "Source Type", "Usage %", "Trustworthiness Rating", "Source"
            ],
            "unmet_needs": [
                "Need Category", "Specific Need", "Priority", "Current Gap", "Source"
            ],
            "treatment_expectations_vs_reality": [
                "Expectation", "Reality", "Gap Severity", "Impact", "Source"
            ],
            "adherence_factors": [
                "Factor Type", "Factor", "Impact on Adherence", "Source"
            ],
            "drop_out_triggers": [
                "Trigger", "Journey Stage", "Impact", "Source"
            ],
            "patient_beliefs_misconceptions": [
                "Belief/Misconception", "Prevalence", "Impact", "Source"
            ],
            "stigmatization": [
                "Type", "Prevalence", "Impact", "Source"
            ],
            "support_systems": [
                "Support Type", "Availability", "Utilization", "Satisfaction", "Source"
            ],
            "cultural_factors": [
                "Factor", "Observation", "Impact on Journey", "Source"
            ],
            "patient_organizations": [
                "Organization", "Focus", "Services", "Contact", "Source"
            ],
            "patient_resources": [
                "Resource", "Provider", "Type", "Access", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return [
            "patient_journey_stages", "journey_pain_points", "emotional_journey",
            "unmet_needs", "adherence_factors", "support_systems"
        ]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: PATIENT EXPERIENCE

### COMPREHENSIVE DATA REQUIREMENTS

1. **Patient Journey Stages**
   - Map the complete journey (12+ steps recommended):
     1. Symptom onset
     2. Self-management attempts
     3. First healthcare contact
     4. Initial diagnosis/misdiagnosis
     5. Treatment initiation
     6. First-line treatment experience
     7. Treatment failure/frustration
     8. Specialist referral
     9. Accurate diagnosis
     10. Treatment escalation
     11. Ongoing management
     12. Long-term outcomes

2. **Journey Pain Points**
   - Specific pain points at each stage
   - Impact and frequency

3. **Emotional Journey**
   - Emotions at each journey step
   - Positive and negative feelings
   - Key emotional triggers

4. **Patient Quotes**
   - Authentic quotes from surveys/studies
   - Context and source

5. **Diagnostic Delay**
   - Factors contributing to delay
   - Average delay duration
   - Impact on outcomes

6. **Information Sources**
   - Where patients get information
   - Trustworthiness ratings
   - Gaps in information

7. **Unmet Needs**
   - Medical needs
   - Non-medical needs
   - Priority ranking

8. **Treatment Expectations vs Reality**
   - What patients expect
   - What they experience
   - Gap analysis

9. **Adherence Factors**
   - Facilitators of adherence
   - Barriers to adherence

10. **Drop-out Triggers**
    - Why patients disengage
    - At which journey stages

11. **Patient Beliefs & Misconceptions**
    - Common beliefs
    - Impact on behavior

12. **Stigmatization**
    - Types of stigma experienced
    - Prevalence and impact

13. **Support Systems**
    - Available support (organizations, family, HCPs)
    - Utilization and satisfaction

14. **Cultural Factors**
    - Country-specific cultural considerations
    - Impact on patient journey

### PATIENT VOICE
Include actual patient quotes where available. These provide authenticity and actionable insights.
"""


class SegmentationDomain(BaseDomain):
    """Domain 6: Patient Segmentation research session - Enhanced."""

    domain_id = 6
    domain_name = "Patient Segmentation"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} age distribution patient demographics {country}",
            "{disease} gender differences women men {country}",
            "{disease} severity classification mild moderate severe refractory",
            "{disease} autoimmune type endotypes phenotypes",
            "{disease} treatment adherence compliance medication {country}",
            "{disease} rural urban healthcare access {country} regional",
            "{disease} undiagnosed undertreated patients delayed diagnosis",
            "{disease} omalizumab responders non-responders",
            "{disease} comorbidity psychiatric mental health anxiety depression",
            "{disease} elderly patients specific needs treatment challenges",
            "{disease} pediatric children prevalence treatment",
            "{disease} angioedema subgroups patient population clinical phenotypes",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "age_segments": [
                "Segment", "Age Range", "Est. Size", "% of Total", "Key Characteristics", "Journey Differences", "Source"
            ],
            "gender_segments": [
                "Segment", "Est. Size", "% of Total", "Key Characteristics", "Journey Differences", "Source"
            ],
            "socioeconomic_segments": [
                "Segment", "Est. Size", "% of Total", "Key Characteristics", "Access Barriers", "Source"
            ],
            "severity_segments": [
                "Segment", "Definition", "Est. Size", "% of Total", "Treatment Pattern", "Outcomes", "Source"
            ],
            "phenotype_segments": [
                "Phenotype", "Est. Size", "% of Total", "Clinical Features", "Treatment Response", "Source"
            ],
            "symptom_presentation_segments": [
                "Phenotype", "Est. Size", "% of Total", "Clinical Features", "Treatment Response", "Source"
            ],
            "comorbidity_segments": [
                "Segment", "Est. Size", "% of Total", "Key Comorbidities", "Impact on Management", "Source"
            ],
            "treatment_response_segments": [
                "Segment", "Est. Size", "% of Total", "Characteristics", "Unmet Needs", "Source"
            ],
            "adherence_segments": [
                "Segment", "Est. Size", "% of Total", "Behavior Pattern", "Drivers", "Source"
            ],
            "healthcare_engagement_segments": [
                "Segment", "Est. Size", "% of Total", "Engagement Pattern", "Intervention Needs", "Source"
            ],
            "information_seeking_segments": [
                "Segment", "Est. Size", "Preferred Sources", "Digital Savvy", "Source"
            ],
            "geographic_segments": [
                "Segment", "Est. Size", "% of Total", "Access Characteristics", "Barriers", "Source"
            ],
            "healthcare_system_segments": [
                "Segment", "Est. Size", "% of Total", "Characteristics", "Source"
            ],
            "provider_relationship_segments": [
                "Segment", "Est. Size", "Characteristics", "Journey Impact", "Source"
            ],
            "underserved_populations": [
                "Population", "Est. Size", "Barriers to Diagnosis/Treatment", "Current Support", "Source"
            ],
            "segment_priority_matrix": [
                "Segment", "Size", "Unmet Need", "Accessibility", "Intervention Potential", "Priority Score", "Source"
            ],
            "expectation_reality_gaps": [
                "Segment", "Patient Expectation", "Clinical Reality", "Gap Severity", "Impact", "Source"
            ],
            "segment_barriers": [
                "Segment", "Primary Barriers", "Secondary Barriers", "Source"
            ],
            "segment_opportunities": [
                "Segment", "Intervention Opportunity", "Potential Impact", "Feasibility", "Source"
            ],
            "cross_segment_analysis": [
                "Segment Combination", "Overlap Size", "Key Characteristics", "Source"
            ],
            "segment_migration_patterns": [
                "From Segment", "To Segment", "Trigger", "Timeframe", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return [
            "age_segments", "severity_segments", "phenotype_segments",
            "treatment_response_segments", "underserved_populations", "segment_priority_matrix"
        ]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: PATIENT SEGMENTATION

### COMPREHENSIVE DATA REQUIREMENTS

Target: 45+ distinct patient segments across categories

1. **Demographic Segments**
   - Age-based (pediatric, young adult, middle-aged, older adult, elderly)
   - Gender-based (with key differences)
   - Socioeconomic (high, middle, low income)

2. **Clinical Segments**
   - Severity-based (mild, moderate, severe, refractory)
   - Phenotype/endotype (Type I, Type IIb, overlap)
   - Symptom presentation (wheals only, wheals+angioedema, angioedema only)
   - Comorbidity clusters (atopic, autoimmune, psychiatric, cardiometabolic)
   - Treatment response (AH responders, biologic responders, non-responders)

3. **Behavioral Segments**
   - Adherence patterns (high, moderate, low, non-adherent)
   - Healthcare engagement (active seekers, compliant, passive, disengaged)
   - Information-seeking behavior (digital natives, traditional, peer-dependent)
   - Self-management capability

4. **Access-Based Segments**
   - Geographic (urban major city, urban smaller city, suburban, rural, remote)
   - Healthcare system (public only, private insurance, mixed)
   - Provider relationship (specialist-managed, GP-managed, fragmented, no regular provider)

5. **Underserved Populations**
   - Undiagnosed population estimate
   - Undertreated population (should be on biologics but aren't)
   - Lost to follow-up
   - Vulnerable populations (elderly with comorbidities, low health literacy, language barriers, mental health comorbidity)

6. **Segment Analysis**
   - Priority matrix (size × unmet need × accessibility × intervention potential)
   - Cross-segment overlaps
   - Migration patterns between segments
   - Expectation vs reality gaps by segment
   - Segment-specific barriers and opportunities

### QUANTIFICATION
For each segment, provide:
- Estimated size (number of patients)
- Percentage of total population
- Key differentiating characteristics
- Journey differences or specific barriers
"""


class StakeholdersDomain(BaseDomain):
    """Domain 7: Stakeholder Mapping research session - Enhanced."""

    domain_id = 7
    domain_name = "Stakeholder Mapping"

    @property
    def search_queries(self) -> List[str]:
        return [
            "{disease} specialist {country} dermatology allergology",
            "{disease} key opinion leader {country} researcher",
            "{country} dermatology university hospital clinic",
            "{country} drug reimbursement authority pharmaceutical",
            "{country} dermatology venereology society professional",
            "{disease} patient organization {country} allergy",
            "{country} medical products agency regulatory authority",
            "{country} regions pharmaceutical recommendations biologics",
            "{disease} UCARE center excellence network",
            "{country} dermatology professor researcher urticaria",
            "Centre for Allergy Research {country}",
            "{country} regions healthcare regional drug committees",
            "European Academy Allergology EAACI {disease} guideline {country}",
            "{country} allergology immunology society professional",
            "{disease} UCARE urticaria center reference excellence",
            "{disease} registry researcher {country}",
            "{country} National Board Health Welfare healthcare guidelines",
        ]

    @property
    def table_schemas(self) -> Dict[str, List[str]]:
        return {
            "specialist_physicians": [
                "Specialty", "Role in Disease", "Est. Number", "Key Influence Points", "Source"
            ],
            "primary_care_providers": [
                "Provider Type", "Role in Disease", "Est. Number", "Key Influence Points", "Source"
            ],
            "nursing_allied_health": [
                "Provider Type", "Role in Disease", "Est. Number", "Key Influence Points", "Source"
            ],
            "clinical_kols": [
                "Name", "Institution", "Position", "Specialty", "Influence Type", "Key Activities", "Source"
            ],
            "research_kols": [
                "Name", "Institution", "Research Focus", "Publications", "Guideline Role", "Source"
            ],
            "guideline_authors": [
                "Name", "Institution", "Guideline Role", "Specialty", "Source"
            ],
            "university_hospitals": [
                "Institution", "Location", "Disease Services", "Key Personnel", "Research Activity", "Source"
            ],
            "specialist_clinics": [
                "Institution", "Location", "Focus", "Patient Volume", "Source"
            ],
            "research_institutions": [
                "Institution", "Research Focus", "Key Projects", "Source"
            ],
            "quality_registries": [
                "Registry Name", "Scope", "Data Collected", "Access", "Source"
            ],
            "national_payer_bodies": [
                "Organization", "Full Name", "Role", "Decision Authority", "Key Contacts", "Source"
            ],
            "hta_bodies": [
                "Organization", "Full Name", "HTA Process", "Recent Disease Decisions", "Source"
            ],
            "regional_payers": [
                "Region/Body", "Role", "Decision Process", "Key Contacts", "Source"
            ],
            "regulatory_bodies": [
                "Organization", "Full Name", "Role", "Key Disease Decisions", "Source"
            ],
            "professional_societies": [
                "Organization", "Full Name", "Focus", "Key Activities", "Website", "Source"
            ],
            "patient_organizations": [
                "Organization", "Focus", "Services", "Membership/Reach", "Key Activities", "Source"
            ],
            "pharma_medical_affairs": [
                "Company", "Products in Disease", "Medical Affairs Focus", "Key Personnel", "Source"
            ],
            "stakeholder_influence_map": [
                "Stakeholder Type", "Influence on Treatment", "Influence on Access", "Influence on Guidelines", "Overall Influence", "Source"
            ],
        }

    @property
    def required_tables(self) -> List[str]:
        return [
            "clinical_kols", "university_hospitals", "national_payer_bodies",
            "professional_societies", "patient_organizations", "stakeholder_influence_map"
        ]

    @property
    def synthesis_prompt(self) -> str:
        return BASE_SYNTHESIS_PROMPT + """

## DOMAIN-SPECIFIC INSTRUCTIONS: STAKEHOLDER MAPPING

### COMPREHENSIVE DATA REQUIREMENTS

1. **Healthcare Provider Stakeholders**
   - Specialist physicians (dermatologists, allergists, immunologists)
   - Primary care providers
   - Nursing and allied health

2. **Key Opinion Leaders (NAMED)**
   - Clinical KOLs: Name, institution, position, specialty, key activities
   - Research KOLs: Name, institution, research focus, publications
   - Guideline authors from {country}

   **CRITICAL**: Include actual names of researchers and clinicians who have:
   - Published on the disease
   - Authored guidelines
   - Led registry studies
   - Conducted clinical trials

3. **Institutional Stakeholders (NAMED)**
   - University hospitals with disease expertise
   - Specialist clinics
   - Research institutions
   - Quality registries

4. **Payer & Policy Stakeholders (NAMED)**
   - National payer bodies (name, role, key contacts if public)
   - HTA bodies (with recent disease-specific decisions)
   - Regional payers
   - Regulatory bodies

5. **Professional Societies**
   - Dermatology societies
   - Allergy/immunology societies
   - International organizations with {country} membership

6. **Patient Organizations**
   - Disease-specific organizations
   - Related organizations (allergy, skin conditions)
   - Services provided

7. **Pharma Medical Affairs**
   - Key companies in the space
   - Their medical affairs activities
   - Key personnel (if publicly available)

8. **Stakeholder Influence Analysis**
   - Who influences treatment decisions
   - Who influences market access
   - Who influences guidelines
   - Overall influence ranking

### NAMED ENTITY REQUIREMENT
This domain requires ACTUAL NAMES of:
- KOLs (researchers, clinicians, guideline authors)
- Institutions (hospitals, research centers)
- Organizations (payer bodies, societies)

Only include names that are:
- Publicly available (publications, websites, LinkedIn)
- Verifiable from search results
- Relevant to {disease} or dermatology/allergy in {country}
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
