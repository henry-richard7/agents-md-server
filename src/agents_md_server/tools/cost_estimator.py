"""cost_estimator tool for MCP.

Estimates monthly and annual costs from Azure Retail Prices API unit prices.
"""

from __future__ import annotations

from fastmcp import FastMCP
from pydantic import BaseModel, Field


class CostEstimatorParams(BaseModel):
    """Parameters for calculating Azure resource cost estimates."""

    unit_price: float = Field(
        ...,
        ge=0.0,
        description="Retail price per unit of measure in USD (from Azure Retail Prices API)",
    )
    unit_of_measure: str = Field(
        ...,
        min_length=1,
        description="The unit of measure, e.g. '1 Hour', '1 GB', '1 Execution', '1 Month'",
    )
    quantity: float = Field(
        ...,
        ge=0.0,
        description="Number of units consumed per month, e.g. 730 for 24/7 VM, 1000000 for 1M executions",
    )
    label: str = Field(
        default="",
        description="Optional label for this line item, e.g. 'D4s v5 VM - East US'",
    )


def register(mcp: FastMCP) -> None:
    """Register the cost_estimator tool with FastMCP."""

    @mcp.tool
    def cost_estimator(
        unit_price: float,
        unit_of_measure: str,
        quantity: float,
        label: str = "",
    ) -> str:
        """Estimate monthly and annual Azure costs from a unit price and usage quantity.

        Takes a unit price (from the Azure Retail Prices API), unit of measure, and monthly quantity.
        Always call this after fetching prices from the azure-pricing skill.
        Returns a formatted cost breakdown with monthly and annual totals.

        Args:
            unit_price: Retail price per unit in USD (must be >= 0).
            unit_of_measure: Unit string, e.g. '1 Hour' or '1 GB'.
            quantity: Monthly usage quantity (must be >= 0).
            label: Optional label or description for this line item.
        """
        # Validate inputs using Pydantic model
        params = CostEstimatorParams(
            unit_price=unit_price,
            unit_of_measure=unit_of_measure,
            quantity=quantity,
            label=label,
        )

        monthly_cost = params.unit_price * params.quantity
        annual_cost = monthly_cost * 12
        label_line = f"### {params.label}\n\n" if params.label else ""

        return (
            f"{label_line}"
            f"- **Unit price:** ${params.unit_price:.6f} per {params.unit_of_measure}\n"
            f"- **Monthly usage:** {params.quantity:,.2f} {params.unit_of_measure}(s)\n"
            f"─────────────────────────────────\n"
            f"- **Monthly cost:** ${monthly_cost:,.4f}\n"
            f"- **Annual cost:**  ${annual_cost:,.4f}\n"
        )
