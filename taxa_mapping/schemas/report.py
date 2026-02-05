from enum import Enum
from typing import List, Optional, Union
from datetime import datetime
from pydantic import BaseModel, Field

class MappingStatus(str, Enum):
    """
    Defines the confidence classification of the taxonomic mapping result.
    
    This enumeration implements a 'traffic light' system to guide user intervention:
    - GREEN: Unambiguous match (automatically accepted).
    - YELLOW_GREEN: High confidence match requiring minimal review.
    - YELLOW: Ambiguous match (multiple candidates or partial synonymy).
    - RED: Low confidence match (weak similarity or excessive ambiguity).
    - BLACK: No correspondence found.
    """
    GREEN = "unambiguous"
    YELLOW_GREEN = "high_similarity"
    YELLOW = "near_tier"
    RED = "low_similarity"
    BLACK = "no_correspondence"


class MappingCandidate(BaseModel):
    """
    Represents a single candidate model from the reference database (AGORA).
    
    This object is used to populate selection lists in the frontend, allowing
    users to manually inspect alternatives if the primary match is not satisfactory.
    """
    model_id: str = Field(
        ..., 
        description="The unique identifier of the AGORA model (typically filename without extension)."
    )
    score: float = Field(
        ..., 
        description="The relevance score assigned by the algorithm (scale 0.0 to 1.0)."
    )
    reason: Optional[str] = Field(
        None, 
        description="A brief rationale explaining why this candidate was selected (e.g., 'exact synonym match')."
    )


class MappingItem(BaseModel):
    """
    Represents the mapping result for a single input query.
    
    It encapsulates the original query, the algorithm's best guess (winner),
    the overall confidence status, and a list of alternative candidates.
    """
    query_name: str = Field(
        ..., 
        description="The original bacterium name provided in the user input."
    )

    mapped_id: Optional[str] = Field(
        None, 
        description="The ID of the preferred/best AGORA model match. Null if status is BLACK."
    )

    status: MappingStatus = Field(
        ..., 
        description="The overall confidence level (traffic light status)."
    )

    confidence_score: float = Field(
        ..., 
        ge=0.0, 
        le=1.0, 
        description="Normalized confidence score between 0.0 and 1.0."
    )

    candidates: List[MappingCandidate] = Field(
        default_factory=list, 
        description="List of all potential AGORA candidates sorted by relevance."
    )

    class Config:
        use_enum_values = True


class MappingReport(BaseModel):
    """
    The final report object structure.
    
    This model serves as the Data Transfer Object (DTO) for saving results to disk
    and communicating with the backend/frontend.
    """
    # Supports both integer (DB ID) and string (Local ID) to ensure compatibility across environments.
    job_id: Union[int, str] = Field(
        ..., 
        serialization_alias="jobId", 
        description="Unique Job Identifier."
    )

    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), 
        description="ISO 8601 timestamp of report generation."
    )

    total_bacteria: int = Field(
        ..., 
        serialization_alias="total_bacteria",
        description="Total number of taxa processed in this job."
    )

    results: List[MappingItem] = Field(
        default_factory=list, 
        description="Detailed list of mapping results for each input taxon."
    )

    def to_json(self) -> str:
        """
        Serializes the report to a JSON string using the defined aliases.
        Crucial for interoperability with the Java Backend (which expects 'jobId').
        """
        return self.model_dump_json(by_alias=True, indent=2)
