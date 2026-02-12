"""All narrative paragraph text constants for fee proposal generation."""

# Introduction paragraph templates

INTRO_COMMON_CORRIDOR_DEPRESSURISATION = (
    "It is understood that mechanical depressurisation systems will be provided "
    "within the stair lobbies. Where such systems are used, it is necessary to "
    "undertake CFD modelling to demonstrate that in the event of a fire, this "
    "system will perform at least as well as a code compliant ventilation system "
    "when the Fire Service are fighting the fire. As such, a scope of works and "
    "fee have been included for this study."
)

INTRO_COMMON_CORRIDOR_EXTENDED_TRAVEL = (
    "The drawings currently show single directional travel distances within the "
    "residential common corridors which exceed the limits given in the standard "
    "design guidance. Whilst it is possible to justify extensions to these "
    "distances by providing mechanical smoke clearance to the corridors, a CFD "
    "modelling study would be required to calculate the required extraction rate "
    "of this system and demonstrate its effectiveness. As such, a scope of works "
    "and fee have been included for this study."
)

INTRO_OPEN_PLAN = (
    "The design currently includes open-plan dwelling layouts which exceed the "
    "design limits stated in the design guidance. Fire Dynamics has developed a "
    "bespoke methodology for justifying such layouts. This method involves "
    "conducting a semi-probabilistic, comparative assessment to show that in the "
    "event of a fire, the probability of an occupant being trapped or harmed in "
    "the proposed open plan design is less than that of an enclosed code "
    "compliant design. As such, a scope of works and fee have been included for "
    "this study."
)

INTRO_WAREHOUSE_CFD = (
    "We understand that the warehouse will feature travel distances that exceed "
    "those stated in the design guidance. In order to justify these travel "
    "distance extensions, a CFD modelling study will need to be undertaken. This "
    "type of analysis would require the use of FDS (Fire Dynamics Simulator) to "
    "model the movement, temperature and visibility of smoke. Subsequently, the "
    "changing internal conditions will be compared with the times taken for "
    "persons to evacuate once an alarm has been raised to show that the occupants "
    "can escape safely should fire occur. As such, a scope of works and fee have "
    "been included for this study."
)

INTRO_WAREHOUSE_STRUCTURAL = (
    "We understand that the warehouse will be provided with freestanding "
    "mezzanine structures.  Given that a suppression system is to be provided, "
    "it is possible to show that passive fire protection to all load-bearing "
    "elements of structure which support these floors (columns / beams / bracing "
    "/ floors) can be safely omitted due to the enhanced degree of structural "
    "fire protection provided by a suppression system. This requires a combined "
    "CFD/Finite Element Analysis to be undertaken to show that should fire "
    "occur, failure of the structure will not occur during the evacuation of the "
    "building or during fire fighting operations. This document details a scope "
    "of works and fee for this study. "
)

INTRO_LONDON_PLAN_AND_GATEWAY = (
    "We understand our involvement will be to provide a major application fire "
    "statement as per Policy D12B of the London Plan). In addition, the building "
    "would be considered a higher risk building under the Building Safety Act "
    "2022. As such, a Gateway 1 fire statement will need to be submitted to the "
    "Building Safety Regulator as part of the Planning Application. Our fee "
    "includes for the production of both statements as well as our assistance "
    "with the development of the design is suitable to meet the requirements of "
    "both processes."
)

INTRO_LONDON_PLAN_ONLY = (
    "We understand our involvement will be to provide a major application fire "
    "statement as per Policy D12B of the London Plan). Our fee includes for the "
    "production of this statement as well as our assistance with the development "
    "of the design is suitable to meet the requirements of the London Plan."
)

INTRO_GATEWAY_ONLY = (
    "The building would be considered a higher risk building under the Building "
    "Safety Act 2022. As such, a Gateway 1 fire statement will need to be "
    "submitted to the Building Safety Regulator as part of the Planning "
    "Application. Our fee includes for the production of this statement as well "
    "as our assistance with the development of the design is suitable to meet "
    "the requirements of this legislation. "
)

INTRO_APPENDIX_REFERENCE = (
    "A detailed scope of works is provided in Appendix A of this document. "
    "Our proposed fees and terms of business are set out in the sections which "
    "follow."
)

# Terms of business

TERMS_ACE = (
    "This proposal is based on the ACE Short Form Agreement 2015 (unamended) "
    "with an aggregate limit to liability equal to the extent of professional "
    "indemnity insurance offered. Should other terms of business be proposed, "
    "this may affect the fees quoted in this letter and until such point where "
    "alternative contract terms are agreed in writing and signed by both "
    "parties, this fee proposal and the ACE Short Form Agreement remain in "
    "place. Our standard period of liability following completion of the works "
    "is 5 years. Should alternative terms of business be proposed, a charge of "
    "\u00a31,500{vat_text} for external review of the terms is required."
)

TERMS_INVOICING = (
    "Invoices will be issued on a monthly basis to reflect the work completed. "
    "Our standard terms are for payment to be received in our bank account "
    "within 30 days of the date our invoice is issued."
)

TERMS_CLOSING = (
    "I trust this provides you with the information that you require, however, "
    "should you wish to discuss, please do not hesitate to contact me. "
)

HOURLY_RATES = [
    ("Fire Engineer", "\u00a3125/hour"),
    ("Senior Fire Engineer", "\u00a3150/hour"),
    ("Associate / Director", "\u00a3200/hour"),
]

OFFICE_ADDRESS = ["Aviation House", "125 Kingsway", "London", "WC2B 6NH"]

# APPENDIX A - Scope text

STAGE_1_SCOPE = [
    "Carry out a desktop review of the client requirements and business case "
    "and provide advice as to any recommendations that would benefit or affect "
    "the project either architecturally or financially.",
]
STAGE_1_DELIVERABLES = [
    "Our key deliverable will be a high level statement of requirements and "
    "basis of design document.",
]

STAGE_2_SCOPE = [
    "Carry out a desktop review of the current design to determine if the "
    "functional requirements of the Building Regulations are achieved.",
    "Identify where a fire engineered (non-standard) approach could add value "
    "by reducing build costs, shortening the construction programme or "
    "enhancing the design (e.g. increasing net area, flexibility and functionality).",
    "Support the development of the design in relation to:",
]
STAGE_2_SUB_BULLETS = [
    "Structural design: the degree of fire resistance needed for all loadbearing elements of structure;",
    "Architectural design: identify where walls, partitions and facades are "
    "required to be fire resisting, advise on travel distances, layouts, staircase numbers and widths;",
    "Service design: fire-fighting provisions (i.e. dry risers, fire-fighting "
    "lifts, hydrants), smoke ventilation, automatic fire suppression systems, fire alarm and detection systems.",
]
STAGE_2_DELIVERABLES = [
    "Our key deliverable will be a high level fire strategy report that is "
    "suitable for supporting the design and assisting with the planning "
    "submission with fire strategy drawings.",
]

LONDON_PLAN_INTRO = [
    "Policy D12B of the London Plan states that all major development proposals should be submitted with a fire statement.",
    "The fire statement document will define the fire safety objectives and "
    "performance requirements of the development alongside and how these "
    "objectives are to be satisfied. Our scope of work will be as follows: ",
]
LONDON_PLAN_SCOPE = [
    "Submission of RFI\u2019s to the design team in order to obtain all relevant information.",
    "Review the relevant information and suggest where changes need to be made "
    "to meet the requirements of Policy D12B of the London Plan (if required).",
    "Once information is received, the fire statement is to be submitted in the "
    "format required, including information relating to (but not limited to):  ",
]
LONDON_PLAN_SUB_BULLETS = [
    "The buildings construction method and products and materials used.",
    "Means of escape for all building users and evacuation strategy.",
    "Passive and active fire safety measures. ",
    "Access and facilities for the fire and rescue service. ",
    "Site access for the fire and rescue service. ",
    'Future development of the asset and the "Golden Thread" of information.',
]
LONDON_PLAN_DELIVERABLES = [
    "Our key deliverable will be a high level fire strategy report that is "
    "suitable for supporting the design and assisting with the planning "
    "submission with fire strategy drawings.",
]

GATEWAY_INTRO = [
    "As the building qualifies as a Higher Risk Building under the Building "
    "Safety Act 2022, it is necessary to submit a Gateway 1 fire statement to "
    "the Building Safety Regulator as part of the planning process",
    "The fire statement document will define the fire safety objectives and "
    "performance requirements of the development alongside and how these "
    "objectives are to be satisfied. Our scope of work will be as follows: ",
]
GATEWAY_SCOPE = [
    "Submission of RFI\u2019s to the design team in order to obtain all relevant information.",
    "Review the relevant information and suggest where changes need to be made "
    "to meet the requirementsof the Building Safety Regulator.",
    "Once information is received, the fire statement is to be submitted in the "
    "format required, including information relating to (but not limited to):  ",
]
GATEWAY_SUB_BULLETS = LONDON_PLAN_SUB_BULLETS
GATEWAY_DELIVERABLES = LONDON_PLAN_DELIVERABLES

STAGE_3_SCOPE_WITH_STAGE_2 = [
    "Continue providing fire safety advice to allow the design to be suitably "
    "developed to commence consultation with the Approving Authorities.",
]
STAGE_3_SCOPE_WITHOUT_STAGE_2 = [
    "Carry out a desktop review of the current design to determine if the "
    "functional requirements of the Building Regulations are achieved.",
    "Where required, propose solutions to aspects of the design that deviate from standard guidance.",
    "Identify where a fire engineered (non-standard) approach could add value "
    "by reducing build costs, shortening the construction programme or "
    "enhancing the design (e.g. increasing net area, flexibility and functionality).",
]
STAGE_3_COMMON_SCOPE = ["Support the development of the design in relation to:"]
STAGE_3_SUB_BULLETS = STAGE_2_SUB_BULLETS
STAGE_3_DELIVERABLES_TEMPLATE = (
    "The information above will be documented in a detailed fire safety strategy "
    "which will be suitable for submission to the Approving Authorities. This "
    "strategy will demonstrate how the building complies with the functional "
    "requirements of {legislation} and will also include:"
)
STAGE_3_DELIVERABLES_SUB_BULLETS = [
    "Preliminary calculations and sketches to support any alternative design solutions;",
    "Marked up fire strategy drawings; and",
    "Performance specifications for active fire safety systems to allow the "
    "detailed design of the system to be progressed by the appropriate design engineer.",
]

STAGE_4_SCOPE_WITHOUT_STAGE_3 = [
    "Carry out a desktop review of the current design to determine if the "
    "functional requirements of the Building Regulations are achieved.",
    "Identify where a fire engineered (non-standard) approach could add value "
    "by reducing build costs, shortening the construction programme or "
    "enhancing the design (e.g. increasing net area, flexibility and functionality).",
]
STAGE_4_SCOPE = [
    "A detailed and refined fire strategy report will be prepared during Stage "
    "4 which will summarise the strategy to date and allow detailed discussions "
    "with the approving authorities to commence. ",
    "Fire strategy marked-up drawings will be produced to allow the architect to develop the scaled fire strategy drawings. ",
    "Outline performance specifications for each of the different systems will "
    "be developed to allow the detailed design of the system/s to be progressed "
    "by the appropriate design engineer. ",
    "All calculations which are required to support the fire strategy will be "
    "undertaken in Stage 4. The outputs of the calculations will inform the "
    "fire strategy requirements to enable the developed design to be finalised "
    "and incorporated into the respective drawings / designs. ",
    "If required, we will advise on the phasing of the works with regard to "
    "fire strategy compliance in respect of sectional completion, however this "
    "will only be a bullet point list of the key considerations. ",
    "Provide continued support to the design team with the integration of the "
    "recommendations of the detailed fire safety strategy into their technical design information. ",
    "Where required, provide alternative solutions to address issues raised by "
    "design team members or sub-contractors including value engineering exercises. ",
]
STAGE_4_DELIVERABLES_TEMPLATE = (
    "A fire strategy report and associated documentation which incorporates any "
    "design team and approving authorities comments and alterations to the "
    "design during Stage 4. This report will also finalise any calculations "
    "required to demonstrate compliance with {legislation}. "
)

COMMON_CORRIDOR_INTRO = (
    "The design features travel distances within the common corridors which "
    "exceed the limits provided in the standard guidance. As such, a fire engineered solution is proposed. "
)
COMMON_CORRIDOR_SOLUTION = (
    "This solution involves providing mechanical smoke shafts within the common "
    "corridor. Upon the detection of smoke, the system will move smoke away "
    "from the stair and provide clearance to the whole length of the corridor. "
    "This is an enhancement over a code compliant system where the only "
    "objective is to keep the stair clear of smoke and, therefore, can be used "
    "to justify travel distances which exceed the code compliant maximum. "
)
COMMON_CORRIDOR_CFD_INTRO = (
    "This solution will require a CFD modelling study to calculate the required "
    "extraction rate of the system and demonstrate its effectiveness. The scope of works for this study will be as follows: "
)
COMMON_CORRIDOR_SCOPE = [
    "Meet with the approving authorities to agree the required inputs for the model including fire sizes, fire locations and timelines. ",
    "Build a computational 3D model of all relevant spaces and run models for each scenario required by the approving authorities (no more than {num_models} envisaged). ",
    "Collate the results of the modelling into a stand-alone report which will detail the inputs, methodology and results of the study. ",
    "Meet with the approving authorities to present the results and conclusions of the study. If necessary, the report and / or modelling will be revised to achieve Building Regulations approval. ",
]

OPEN_PLAN_INTRO_TEMPLATE = (
    "The design features apartments which have open plan layouts which do not "
    "meet the guidance of BS 9991. As such, further work is required to "
    "demonstrate that these layouts comply with the functional requirements of {legislation}. "
)
OPEN_PLAN_METHODOLOGY = [
    "Fire Dynamics has developed a unique approach to open plan residential "
    "modelling and has a proven track record in gaining approval for open plan arrangements of various sizes across the UK. ",
    "Our approach is to model multiple fire scenarios for both a code compliant "
    "design and the proposed design to determine the probability that an "
    "occupant will be able to escape both when the fire safety measures operate "
    "and when they fail. These results are fed into event trees to determine an "
    "overall risk that an occupant could become trapped for both designs. ",
]
OPEN_PLAN_ANTICIPATED_TEMPLATE = (
    "It is anticipated that the results will show that the risk of an occupant "
    "becoming trapped under the proposed design is lower than in a comparable "
    "code compliant design and, as such, the proposed design can be assumed to "
    "comply with the functional requirements of {legislation}. "
)
OPEN_PLAN_SCOPE = [
    "Produce a proposal document to agree the required inputs for the model including fire sizes, fire locations and timelines. ",
    "Build a computational 3D model of the space and run fire models for both a code compliant and proposed layout (no more than {num_models} scenarios envisaged). ",
    "Using Microsoft Excel, determine the probability of failure in all scenarios and feed these results into event trees to calculate the overall probability of failure in each case. ",
    "Collate the results of the modelling into a standalone report which will detail the inputs, methodology and results of the study. The CFD data and associated spreadsheets will also be provided for review. ",
    "Meet with the approving authorities to present the results and conclusions of the study. If necessary the report and / or modelling will be revised to allow the scheme to achieve Building Regulations approval. ",
]

WAREHOUSE_CFD_INTRO = (
    "The design features travel distances that exceed those stated in the design guidance.  "
    "In order to justify these travel distance extensions, a CFD modelling study will need to be undertaken. "
    "This type of analysis would require the use of FDS (Fire Dynamics Simulator) to model the movement, "
    "temperature and visibility of smoke. Subsequently, the changing internal conditions will be compared "
    "with the times taken for persons to evacuate once an alarm has been raised. The scope of works for this study will be as follows: "
)
WAREHOUSE_CFD_SCOPE = [
    "Meet with the approving authorities to agree the required inputs for the model including fire sizes, fire locations and timelines. ",
    "Build a computational 3D model of all relevant spaces and run models for each scenario required by the approving authorities (no more than {num_models} envisaged). ",
    "Calculate the time taken for all occupants within the warehouse to reach a place of relative safety (i.e. outside the building or within a protected stair). ",
    "Collate the results of the modelling into a stand-alone report which will detail the inputs, methodology and results of the study and demonstrate that the time taken for occupants to escape is less than the time taken for conditions within the space to become untenable. ",
    "Meet with the approving authorities to present the results and conclusions of the study. If necessary, the report and / or modelling will be revised to achieve Building Regulations approval. ",
]

STRUCTURAL_FE_INTRO = (
    "We will show that the passive fire protection to all load-bearing elements "
    "of structure which support the mezzanine (columns / beams / bracing / "
    "floors) can be safely omitted due to the enhanced degree of structural "
    "fire protection provided by the buildings suppression system. To achieve "
    "this, a combined CFD (Computational Fluid Dynamics) and Finite Element "
    "Analysis will be undertaken. Specifically, the scope of works for this study will be as follows:"
)
STRUCTURAL_FE_SCOPE = [
    "Undertake a Qualitative Design Review with the approving authorities to agree the inputs, methodology and failure criteria for the study.",
    "Undertake a CFD assessment (Fire Dynamics Simulator) to measure the expected temperatures adjacent to all elements of structure when subjected to two fires, specifically:",
]
STRUCTURAL_FE_SUB_BULLETS_1 = [
    "A growing fire with a heat release rate capped by the activation of the suppression system; and",
    "A growing fire which is allowed to grow for the duration of the simulation (assumed suppression failure).",
]
STRUCTURAL_FE_SCOPE_2 = [
    "Undertake a Finite Element Analysis to assess the performance of the structure under the heating regimes calculated by the CFD assessments. The results of these assessments will be compared against the agreed failure criteria. It is anticipated that the results will show:",
]
STRUCTURAL_FE_SUB_BULLETS_2 = [
    "When the suppression system activates, the structure will not fail for the duration of the simulation. Therefore, it is reasonable to assume the structure will remain stable during evacuation and when the Fire Service attempt to fight the fire; and",
    "When the suppression system fails, the structure will remain stable for a sufficient period of time to allow the evacuation of the building.",
]
STRUCTURAL_FE_SCOPE_3 = [
    "Collate the results of the study into a stand-alone report which will detail the inputs, methodology and results of the study.",
    "Meet with the Approving Authorities to present the results and conclusions of the study.",
    "If necessary, revise the report / study one time to account for any adverse comments raised by the Approving Authorities.",
]

CONSTRUCTION_ADVICE_INTRO = (
    "We will, on request, provide general, ad-hoc fire engineering advice "
    "during the construction stages to aid the design team and contractor in the following: "
)
CONSTRUCTION_ADVICE_SCOPE = [
    "Understanding and implementing the strategy; ",
    "Avoiding misinterpretation which can add cost to a scheme; ",
    "Responding to design alterations that are made during the construction stage; ",
    "Evaluating value engineering proposals; ",
    "Evaluating alternative designs/materials put forward by the principal contractor or the sub-contractors; ",
    "Provision of support to the principal contractor and/or nominated sub-contractors to facilitate completion of all requisite commissioning and certification activity; and",
    "Outline the implications of the fire strategy on the fire management of the building post completion (RRO). This would be a bullet point type list within the fire strategy report only. ",
]
CONSTRUCTION_ADVICE_DELIVERABLES = [
    "Provide on-going support during construction on an ad-hoc/as requested basis; ",
    "Update the fire strategy report at 90% and 100% completion; ",
]

SITE_VISITS_SCOPE = [
    "Attend site to review the completed or partially completed construction details.  The scope of such visits and level of reporting required would need to be agreed prior to attendance. ",
]
SITE_VISITS_DELIVERABLES = [
    "Provide a short form report highlighting the findings of any site visit.  The scope and format of any such report would be agreed prior to attendance on site. ",
]

PHASED_OCCUPATION_INTRO = (
    "Where a phased occupation strategy is proposed, we will prepare a document "
    "which demonstrates that for each phase, a suitable level of safety is achieved in the occupied areas. Specifically, we will:  "
)
PHASED_OCCUPATION_SCOPE = [
    "Assist in the production of the contractors phased handover strategy. ",
    "Provide advice as to the required fire safety provisions within each occupied area during each phase. this will include recommendations for: ",
]
PHASED_OCCUPATION_SUB_BULLETS = [
    "Means of escape; ",
    "Passive fire protection systems such as structural fire protection and compartmentation; ",
    "Active fire safety systems such as fire detection and alarm, automatic fire suppression and smoke control systems; and",
    "Facilities for fire service intervention and access. ",
]
PHASED_OCCUPATION_DELIVERABLES_TEMPLATE = (
    "A document which demonstrates that for each phase, the level of safety "
    "achieved in each occupied area is in compliance with {legislation}. This "
    "report will be revised once, if necessary, following discussion with the relevant stakeholders. "
)

CFSMP_INTRO = (
    "We will provide advice on the fire safety during construction in order to "
    "assist the contractor in identifying the main causes of accidents and ill "
    "health, and to eliminate the hazards and control the risks. This will "
    "support the Contractor\u2019s responsibilities under the Construction (Design and Management) Regulations 2015. Specifically, we will:"
)
CFSMP_SCOPE = [
    "Prepare a Construction Fire Safety Plan in accordance with the guidance "
    "contained within the Health and Safety Executive Publication HSG168 Fire "
    "Safety in Construction. This would address the following aspects for implementation and management by the contractor: ",
]
CFSMP_SUB_BULLETS = [
    "Reducing ignition sources. ",
    "Reducing potential fuel sources. ",
    "General fire precautions ",
    "Emergency procedures ",
    "Higher fire risk methods and materials of construction. ",
    "Guidance for multi-storey buildings (if applicable). ",
]

CONSTRUCTION_RA_TEXT = [
    "Following the production of the Construction Fire Safety Management Plan, it is necessary to carry out periodic Fire Risk Assessments (FRA) in order to verify that those fire precautions are being correctly implemented. ",
    "The scope includes for one fire risk assessment every three months. Following each Fire Risk Assessment, we would produce a report documenting the results of the inspection and highlighting any issues which were identified. ",
]

REG38_TEXT = [
    "Regulation 38 of the Building Regulations requires that, on practical completion of the project, the main contractor should ensure that a pack of information is provided for the operator to ensure that they have the information required to manage the fire safety of the building. ",
    "This pack of information should include details such as an as-built fire strategy report as well as as-built details of key fire safety systems. ",
    "We will produce a short report giving a summary of the key fire safety issues for the building. With regards to all other required documentation, we would produce a summary list of the information required and would coordinate the pack into a format suitable for submission.  ",
]

EWS1_INTRO = (
    "Our involvement would be to undertake a review of the building, focused "
    "on the risks within the external walls (including attachments). The "
    "purpose of this is to produce a report suitable for submission to the "
    "mortgage providers of current leaseholders and prospective purchasers. "
)
EWS1_SCOPE = [
    "Review of the as-built drawings with relation to fire safety. ",
    "Review of a suitably qualified surveyors intrusive survey of the as-built construction. ",
    "Production of a report, assessing the risk of fire spread within the external wall construction and comparing to best practice / government guidelines. ",
]
EWS1_FOLLOWING = "Following this review: "
EWS1_FOLLOWING_SCOPE = [
    "If Fire Dynamics is satisfied that the design and construction is of a sufficiently low level of risk, produce a summary letter of comfort (LOC) with an EWS1 form appended. ",
    "If Fire Dynamics is not satisfied that the design and construction is of a sufficiently low level of risk, a conclusion as such will be included within the report and no EWS1 or LOC would be issued. Should it be deemed that the risk is not sufficiently low, the reasons will be stated, but no advice on the type of remedial work required will be provided. ",
]
EWS1_EXCLUSIONS_INTRO = "The following would not form part of this scope and would be expected to be provided by others: "
EWS1_EXCLUSIONS = [
    "Intrusive investigation of cavity barriers; ",
    "Fire testing, but high-level advice can be provided by Fire Dynamics, which may incur additional fees; ",
    "Intrusive investigation of external wall; ",
    "Fire risk assessment; ",
    "Post analysis support (i.e. advice on any shortcomings highlighted); and ",
    "Fire safety review of items not related to external wall areas. ",
]

COMPLETION_RA_TEXT = [
    "During the construction phase we will undertake a pre-occupation fire safety risk assessment to ensure that the fire strategy design and completed building has provided the necessary facilities to enable the building to comply with The Regulatory Reform (Fire Safety) Order 2005 or where located within Scotland, to the Fire (Scotland) Act 2005.  ",
    "As a project nears completion (but not complete for handover), the aim of a pre-occupation fire risk assessment is to provide the client with a document that shows that suitable and sufficient documentation has been put in place to enable them to occupy the building with a high degree of assurance that the primary legislative requirements relating to fire safety have been satisfied. ",
    "This would ensure that all relevant information relating information relating to emergency procedures for evacuation are established, emergency assembly points had been identified and the client advised on the correct channels to communicate information to the enforcing authorities, handling, storage and control over hazardous substances on site. ",
    "This service would involve a range of services from assessment, inspection, audit and liaison with other stakeholders which enabled the client to evolve from a position of non-compliance to compliance within a pre-occupation time-frame following practical completion of the construction / fit-out phase. ",
]

PEER_REVIEW_SCOPE = [
    "Review of a suitably qualified surveyors intrusive survey of the as-built construction. ",
    "Meet with the project fire engineer and Approved Inspector to discuss the work undertaken to date and agree a way forward for the modelling study to demonstrate compliance.",
    "Review the fire safety engineering report provided by the project fire engineer with emphasis on the following: ",
]
PEER_REVIEW_SUB_BULLETS = [
    "Review of fire engineering methodology adopted and suitability for the design. ",
    "Review of input parameters, assumptions and proposed tenability criteria. ",
    "Review of results from model outputs and conclusions drawn from them.  ",
]
PEER_REVIEW_SCOPE_2 = [
    "Input files for CFD Modelling will also undergo detailed review to ensure the input parameters specified in the report align with what has been constructed and modelled. ",
    "The output files/results of CFD Modelling will also undergo detailed review to determine if the conclusions drawn in the report align with the results obtained.  ",
    "Identify aspects of the CFD that requires further explanation to demonstrate compliance with the Building Regulations.  ",
    "A third party review report will be provided which will state the professional opinion of Fire Dynamics Group. The report will be submitted to Building Control to aid in their determination on whether the fire engineering report suitably demonstrates that building design meet the functional requirements of the Building Regulations.",
]

CLIENT_MONITORING_INTRO = (
    "We will, on request, provide general, ad-hoc fire engineering advice "
    "during the construction stages to aid the client team and by, on behalf "
    "of the client team, reviewing the contractor team in their implementation "
    "of the fire strategy by providing the following support: "
)
CLIENT_MONITORING_SCOPE = [
    "Understanding and implementing the strategy (prepared by others);",
    "Avoiding misinterpretation which can add cost to a scheme; ",
    "Responding to design alterations that are made during the construction stage; ",
    "Evaluating value engineering proposals; ",
    "Evaluating alternative designs/materials put forward by the principal contractor or the sub-contractors; ",
    "Provision of support to the principal contractor and/or nominated sub-contractors to facilitate completion of all requisite commissioning and certification activity (responsibility lies with those parties); ",
    "Review of fire engineering methodology adopted and suitability for the design. ",
    "Review of input parameters, assumptions and proposed tenability criteria. ",
    "Review of results from model outputs and conclusions drawn from them.  ",
    "Outline the implications of the fire strategy on the fire management of the building post completion (RRO). This would be a bullet point type list report only to aid the client in understanding of their obligations based on the works undertaken;",
    "Attend site to review the completed or partially completed construction details.  The scope of such visits and level of reporting required would need to be agreed prior to attendance. However it is typically expected that attendance will be an average of once per month (aligned with site meetings) with an additional site visit at Practical Completion to review C&E witnessing with the client team.",
]
CLIENT_MONITORING_DELIVERABLES = [
    "Provide on-going support during construction on an ad-hoc/as requested basis; ",
    "Where necessary, attend fire engineering workshops or design team meetings to discuss the scheme (an average of 1 meeting per month is included in this scope); and",
    "Provide a short form report highlighting the findings of any site visit.  The scope and format of any such report would be agreed prior to attendance on site. ",
]
CLIENT_MONITORING_CLOSING = (
    "One revision of the peer review report should any changes to the study be "
    "made by the project fire engineer following discussion."
)

# APPENDIX B - Exclusions

EXCLUSIONS_INTRO = (
    "Whilst many of the techniques we use are relatively simple in engineering "
    "terms, some are highly sophisticated and take many days of computational "
    "time. It is for this reason that we need to eliminate these types of "
    "analysis from our standard set of deliverables. Specifically, these are:"
)
EXCLUSIONS_PEER_REVIEW = (
    "Our scope of work involves provision of independent third party review "
    "services only. As such, all fire safety engineering design work is "
    "excluded from our deliverables. Alternative design solutions and general "
    "design work will not be provided as part of our independent review scope of works. "
)
EXCL_STRUCTURAL_FE_INCLUDED = " - Advanced structural fire engineering techniques, beyond those detailed in this scope, are not included in this proposal."
EXCL_STRUCTURAL_FE_NOT_INCLUDED = " - We do not envisage that advanced structural fire engineering techniques would offer any benefit to this project."
EXCL_EVAC_MODELLING = " - We do not anticipate that evacuation modelling will be necessary at the current time."
EXCL_SMOKE_MODELLING_INCLUDED = " - CFD Modelling studies, outside of those detailed in the scope, are not included in this proposal."
EXCL_SMOKE_MODELLING_NOT_INCLUDED = " - We do not envisage that CFD Modelling techniques would offer any benefit to this project."
EXCL_FIRE_STRATEGY_DRAWINGS = " - Fire strategy drawings will be provided in PDF format to allow the relevant information to be inputted into CAD drawings or BIM models by other members of the design team, as necessary."
EXCL_EXTERNAL_WALLS_WITH_EWS1 = ' - The scope includes for the provision of EWS1 forms upon completion. Any other works relating to on-statutory "letters of comfort" required by external parties are not included in this proposal.'
EXCL_EXTERNAL_WALLS_WITHOUT_EWS1 = ' - The completion of EWS1 forms, or other non-statutory "letters of comfort" required by external parties are not included in this proposal.'
EXCL_FIRE_STRATEGY_DEV = "\u2013 Our fee is for the specialist works detailed in the scope only. Our work will be based on the assumptions in the fire strategy information provided by others. This fee does not include for Fire Dynamics taking ownership of the fire strategy."
EXCL_LETTERS_OF_COMFORT = ' - The completion of EWS1 forms, or other non-statutory "letters of comfort" required by external parties are not included in this proposal.'
EXCL_SITE_VISIT_RECORDS = "\u2013 Any items highlighted within site visits will be recorded either by the project site software or by post visit report, not both."
EXCL_SITE_VISIT_VALIDITY = ' - Site visit records are not to be relied upon as an exhaustive list, they are provided as a summary of items seen at the time of visit or as examples of potential issues. Therefore, they are not to be viewed as a "snagging list" and others are responsible for ensuring that the same, similar or related issues are resolved in other areas or at other times.'
