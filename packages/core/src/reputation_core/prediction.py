"""Validated binary probabilities and deterministic prediction credit."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BinaryPrediction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    p_yes: float = Field(ge=0, le=1, allow_inf_nan=False)
    p_no: float = Field(ge=0, le=1, allow_inf_nan=False)
    final_outcome: Literal["yes", "no"]

    @model_validator(mode="after")
    def require_probability_sum(self) -> Self:
        if abs(self.p_yes + self.p_no - 1.0) > 1e-9:
            raise ValueError("p_yes and p_no must sum to 1 within 1e-9")
        return self

    @property
    def outcome_probability(self) -> float:
        return self.p_yes if self.final_outcome == "yes" else self.p_no

    @property
    def credit(self) -> float:
        outcome = 1.0 if self.final_outcome == "yes" else 0.0
        return 100.0 * (1.0 - (self.p_yes - outcome) ** 2)
