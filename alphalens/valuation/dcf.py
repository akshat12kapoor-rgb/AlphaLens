"""
Discounted cash flow.

Stage 1 grows free cash flow at a constant rate; stage 2 fades that rate
linearly to the terminal rate; the Gordon Growth Model capitalises what comes
after. Set stage2_years to 0 for a plain two-stage model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DCFResult:
    projected_fcf: list[float] = field(repr=False)
    present_values: list[float] = field(repr=False)
    growth_rates: list[float] = field(repr=False)
    terminal_value: float = 0.0
    pv_terminal_value: float = 0.0
    total_pv: float = 0.0
    intrinsic_value: float = 0.0
    stage1_years: int = 5
    stage2_years: int = 0

    @property
    def stage1_pv(self) -> float:
        return sum(self.present_values[:self.stage1_years])

    @property
    def stage2_pv(self) -> float:
        return sum(self.present_values[self.stage1_years:])

    @property
    def year_labels(self) -> list[str]:
        return [f"Year {t}" for t in range(1, len(self.projected_fcf) + 1)]


def _validate_growth_rate(growth_rate: float) -> None:
    if growth_rate <= -1:
        raise ValueError(
            f"Growth rate ({growth_rate:.1%}) cannot be -100% or lower - "
            "cash flow can't shrink past zero.")


def validate(wacc: float, terminal_growth: float, growth_rate: float | None = None) -> None:
    """Guard the inputs that break the model.

    `growth_rate` is optional because callers checking only the discounting
    inputs (the sensitivity grid, say) may not have one in hand yet; `run()`
    and `project()` always pass theirs. The UI clamps its slider to [0%, 40%],
    but both are public and used directly by tests, the CLI and each other.
    """
    if wacc <= 0:
        raise ValueError("The discount rate must be positive.")
    if terminal_growth < 0:
        raise ValueError("Terminal growth cannot be negative.")
    if wacc <= terminal_growth:
        raise ValueError(
            f"The discount rate ({wacc:.1%}) must exceed terminal growth "
            f"({terminal_growth:.1%}), or the Gordon Growth Model gives an "
            "infinite terminal value.")
    if growth_rate is not None:
        _validate_growth_rate(growth_rate)


def growth_path(growth_rate: float, terminal_growth: float, stage1_years: int,
                stage2_years: int) -> list[float]:
    """Constant through stage 1, then a straight line down to terminal growth."""
    path = [growth_rate] * stage1_years
    for step in range(1, stage2_years + 1):
        path.append(growth_rate + (terminal_growth - growth_rate) * (step / stage2_years))
    return path


def run(base_fcf: float, shares_outstanding: float, growth_rate: float, wacc: float,
        terminal_growth: float, stage1_years: int = 5, stage2_years: int = 0) -> DCFResult:
    """Value one share from free cash flow."""
    validate(wacc, terminal_growth, growth_rate)
    if not base_fcf or base_fcf <= 0:
        raise ValueError("A DCF needs positive free cash flow.")
    if not shares_outstanding or shares_outstanding <= 0:
        raise ValueError("A DCF needs a share count.")

    rates = growth_path(growth_rate, terminal_growth, stage1_years, stage2_years)
    projected, present, previous = [], [], base_fcf
    for year, rate in enumerate(rates, start=1):
        previous *= (1 + rate)
        projected.append(previous)
        present.append(previous / (1 + wacc) ** year)

    terminal = projected[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    pv_terminal = terminal / (1 + wacc) ** len(rates)
    total = sum(present) + pv_terminal

    return DCFResult(projected_fcf=projected, present_values=present, growth_rates=rates,
                     terminal_value=terminal, pv_terminal_value=pv_terminal, total_pv=total,
                     intrinsic_value=max(total / shares_outstanding, 0.0),
                     stage1_years=stage1_years, stage2_years=stage2_years)


def project(base_value: float, growth_rate: float, terminal_growth: float,
            stage1_years: int = 5, stage2_years: int = 0) -> list[float]:
    """Grow any figure (revenue, say) along the same path, for charting."""
    _validate_growth_rate(growth_rate)
    out, previous = [], base_value
    for rate in growth_path(growth_rate, terminal_growth, stage1_years, stage2_years):
        previous *= (1 + rate)
        out.append(previous)
    return out


def sensitivity(base_fcf: float, shares_outstanding: float, terminal_growth: float,
                stage1_years: int = 5, stage2_years: int = 0,
                wacc_range: list[float] | None = None,
                growth_range: list[float] | None = None) -> pd.DataFrame:
    """Intrinsic value across a discount-rate x growth grid: rows WACC, columns growth."""
    wacc_range = wacc_range or [round(w, 3) for w in np.arange(0.06, 0.161, 0.02)]
    growth_range = growth_range or [round(g, 3) for g in np.arange(0.02, 0.201, 0.03)]

    table = {}
    for wacc in wacc_range:
        row = {}
        for growth in growth_range:
            try:
                row[f"{growth:.0%}"] = round(
                    run(base_fcf, shares_outstanding, growth, wacc, terminal_growth,
                        stage1_years, stage2_years).intrinsic_value, 2)
            except ValueError:
                row[f"{growth:.0%}"] = np.nan
        table[f"{wacc:.0%}"] = row
    frame = pd.DataFrame(table).T
    frame.index.name = "WACC \\ Growth"
    return frame
