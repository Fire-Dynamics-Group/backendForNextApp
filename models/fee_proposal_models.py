from pydantic import BaseModel
from typing import List, Optional
from enum import Enum


class CountryEnum(str, Enum):
    ENGLAND_WALES = "EW"
    JERSEY = "J"


class ClientDetails(BaseModel):
    first_name: str
    surname: str
    address_lines: List[str] = []


class ProjectDetails(BaseModel):
    project_name: str
    project_location: str
    country: CountryEnum = CountryEnum.ENGLAND_WALES


class FeeOptions(BaseModel):
    engineer_name: str
    pii_limit: int = 100000
    include_hourly_rates: bool = False


class ServiceConfig(BaseModel):
    included: bool = False
    fee: float = 0
    optional: bool = False
    limit_meetings: bool = False
    meeting_number: Optional[int] = None
    end_date_month: Optional[str] = None
    end_date_year: Optional[str] = None
    num_models: Optional[int] = None
    extended_travel_distance: bool = False
    hours_per_month: Optional[int] = None
    meetings_per_month: Optional[int] = None


class DesignStagesRiba1to4(BaseModel):
    stage_1: ServiceConfig = ServiceConfig()
    stage_2: ServiceConfig = ServiceConfig()
    london_plan: ServiceConfig = ServiceConfig()
    gateway: ServiceConfig = ServiceConfig()
    stage_3: ServiceConfig = ServiceConfig()
    stage_4: ServiceConfig = ServiceConfig()
    common_corridor_cfd: ServiceConfig = ServiceConfig()
    open_plan_cfd: ServiceConfig = ServiceConfig()
    warehouse_structural: ServiceConfig = ServiceConfig()
    warehouse_cfd: ServiceConfig = ServiceConfig()
    peer_review: ServiceConfig = ServiceConfig()


class DesignStagesRiba5(BaseModel):
    construction_advice: ServiceConfig = ServiceConfig()
    site_visits: ServiceConfig = ServiceConfig()
    site_risk_assessment: ServiceConfig = ServiceConfig()
    cfsmp: ServiceConfig = ServiceConfig()
    phased_occupation: ServiceConfig = ServiceConfig()
    client_monitoring: ServiceConfig = ServiceConfig()


class DesignStagesRiba6(BaseModel):
    regulation_38: ServiceConfig = ServiceConfig()
    ews1_forms: ServiceConfig = ServiceConfig()
    rro_risk_assessment: ServiceConfig = ServiceConfig()


class FeeProposalRequest(BaseModel):
    client: ClientDetails
    project: ProjectDetails
    fee_options: FeeOptions
    design_stages_1_4: DesignStagesRiba1to4 = DesignStagesRiba1to4()
    design_stages_5: DesignStagesRiba5 = DesignStagesRiba5()
    design_stages_6: DesignStagesRiba6 = DesignStagesRiba6()


class EngineerResponse(BaseModel):
    full_name: str
    email_prefix: str
    phone_number: str
    job_title: str
