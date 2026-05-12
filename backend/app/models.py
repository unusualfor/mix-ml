from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

FLAVOR_KEYS = (
    "sweet", "bitter", "sour", "citrusy", "fruity", "herbal",
    "floral", "spicy", "smoky", "vanilla", "woody",
    "minty", "earthy", "umami", "body", "intensity",
)

FlavorValue = Annotated[int, Field(ge=0, le=5)]


# -- ingredient_class -------------------------------------------------------

class ClassNode(BaseModel):
    id: int
    name: str
    is_garnish: bool
    is_commodity: bool
    children: list[ClassNode] = []


class ClassFlat(BaseModel):
    id: int
    parent_id: int | None
    name: str
    is_garnish: bool
    is_commodity: bool


# -- recipe list ------------------------------------------------------------

class RecipeListItem(BaseModel):
    id: int
    name: str
    iba_category: str
    glass: str | None
    ingredient_count: int


class RecipeListResponse(BaseModel):
    total: int
    items: list[RecipeListItem]


# -- recipe detail ----------------------------------------------------------

class IngredientDetail(BaseModel):
    class_id: int
    class_name: str
    amount: float | None
    unit: str | None
    is_optional: bool
    is_garnish: bool
    alternative_group_id: int | None
    raw_name: str | None


class RecipeDetail(BaseModel):
    id: int
    name: str
    iba_category: str
    method: str
    glass: str | None
    garnish: str | None
    source_url: str | None
    ingredients: list[IngredientDetail]


# -- health -----------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str


class ReadyResponse(BaseModel):
    status: str
    db: str


# -- flavor profile ---------------------------------------------------------

class FlavorProfile(BaseModel):
    sweet: FlavorValue
    bitter: FlavorValue
    sour: FlavorValue
    citrusy: FlavorValue
    fruity: FlavorValue
    herbal: FlavorValue
    floral: FlavorValue
    spicy: FlavorValue
    smoky: FlavorValue
    vanilla: FlavorValue
    woody: FlavorValue
    minty: FlavorValue
    earthy: FlavorValue
    umami: FlavorValue
    body: FlavorValue
    intensity: FlavorValue

    @model_validator(mode="before")
    @classmethod
    def _check_all_keys(cls, data):
        if isinstance(data, dict):
            missing = set(FLAVOR_KEYS) - set(data.keys())
            if missing:
                raise ValueError(f"Missing flavor keys: {sorted(missing)}")
            extra = set(data.keys()) - set(FLAVOR_KEYS)
            if extra:
                raise ValueError(f"Unknown flavor keys: {sorted(extra)}")
        return data


# -- bottle -----------------------------------------------------------------

class BottleCreate(BaseModel):
    class_name: str
    brand: str
    label: str | None = None
    abv: Annotated[float, Field(ge=0, le=100)]
    on_hand: bool = True
    flavor_profile: FlavorProfile
    notes: str | None = None


class BottlePatch(BaseModel):
    on_hand: bool | None = None
    flavor_profile: FlavorProfile | None = None
    notes: str | None = None
    label: str | None = None


class BottleOut(BaseModel):
    id: int
    class_id: int
    class_name: str
    family_name: str | None
    brand: str
    label: str | None
    abv: float
    on_hand: bool
    flavor_profile: FlavorProfile
    notes: str | None
    added_at: datetime


class BottleListResponse(BaseModel):
    total: int
    items: list[BottleOut]


class BulkBottleResult(BaseModel):
    inserted: int
    errors: list[dict]


# -- can-make-now -----------------------------------------------------------

class CanMakeSummary(BaseModel):
    total_recipes: int
    can_make: int
    cannot_make: int
    on_hand_classes: int


class CanMakeItem(BaseModel):
    id: int
    name: str
    iba_category: str
    glass: str | None
    can_make: bool
    missing_count: int
    missing_classes: list[str]


class CanMakeResponse(BaseModel):
    summary: CanMakeSummary
    items: list[CanMakeItem]


# -- feasibility detail -----------------------------------------------------

class SatisfyingBottle(BaseModel):
    id: int
    brand: str
    label: str | None


class FeasibilityIngredient(BaseModel):
    class_name: str
    satisfied_by_bottles: list[SatisfyingBottle]
    is_optional: bool
    is_garnish: bool
    is_commodity: bool
    alternative_group_id: int | None


class FeasibilityResponse(BaseModel):
    recipe: RecipeListItem
    can_make: bool
    ingredients: list[FeasibilityIngredient]


# -- optimize-next ----------------------------------------------------------

class OptimizeCurrentState(BaseModel):
    on_hand_class_ids: list[int]
    currently_feasible: int
    currently_feasible_recipes: list[str]


class UnlockedRecipe(BaseModel):
    id: int
    name: str


class EquivalentAlternative(BaseModel):
    class_id: int
    class_name: str
    parent_family: str | None


class RankedCandidate(BaseModel):
    class_id: int
    class_name: str
    parent_family: str | None
    delta: int
    unlocked_recipes: list[UnlockedRecipe]
    equivalent_alternatives: list[EquivalentAlternative] = []


class OptimizeComputation(BaseModel):
    candidates_evaluated: int
    ms: int


class OptimizeNextResponse(BaseModel):
    current_state: OptimizeCurrentState
    ranked_candidates: list[RankedCandidate]
    computation: OptimizeComputation


# -- similar-bottles --------------------------------------------------------

class BottleSummary(BaseModel):
    id: int
    brand: str
    label: str | None
    class_name: str
    parent_family: str | None


class SimilarBottleResult(BaseModel):
    bottle: BottleSummary
    distance: float
    same_family: bool
    top_shared_dimensions: list[str]
    top_differing_dimensions: list[str]


class SimilarBottlesResponse(BaseModel):
    pivot: BottleSummary
    results: list[SimilarBottleResult]


# -- substitutions ----------------------------------------------------------

class SubstitutionCandidate(BaseModel):
    bottle: BottleSummary
    distance: float
    tier: Literal["strict", "loose"]
    rationale: str


class SubstitutionTiers(BaseModel):
    strict: list[SubstitutionCandidate] = []
    loose: list[SubstitutionCandidate] = []


class SubstitutionFeasibility(BaseModel):
    can_make: bool
    missing_count: int


class IngredientAnalysis(BaseModel):
    recipe_ingredient_id: int
    class_name: str
    parent_family: str | None = None
    amount: float | None = None
    unit: str | None = None
    is_satisfied: bool
    anti_doppione_classes: list[str] = []
    satisfied_by_bottles: list[SatisfyingBottle] = []
    substitutions: SubstitutionTiers | None = None
    note: str | None = None


class SubstitutionsResponse(BaseModel):
    recipe: RecipeListItem
    current_feasibility: SubstitutionFeasibility
    ingredients_analysis: list[IngredientAnalysis]


# -- substitution-trace -----------------------------------------------------

class TraceBottleDetail(BaseModel):
    bottle: BottleSummary
    distance: float
    included: bool
    exclusion_reason: str | None = None
    tier: str | None = None


class SubstitutionTraceResponse(BaseModel):
    recipe_ingredient_id: int
    class_name: str
    pivot_profile: dict[str, int] | None
    pivot_source: str
    on_hand_bottles: list[TraceBottleDetail]
