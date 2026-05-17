"""
cost_estimator.py
Estimates monthly and annual costs from Azure Retail Prices API unit prices.
Ported from Azure-Samples/functions-markdown-agent with FastMCP register() pattern.
"""

from pydantic import BaseModel, Field


class CostEstimatorParams(BaseModel):
    unit_price: float = Field(
        description="Retail price per unit of measure (in USD), as returned by the Azure Retail Prices API retailPrice field"
    )
    unit_of_measure: str = Field(
        description="The unit of measure for the price, e.g. '1 Hour', '1 GB', '1 Execution', '1 Month'"
    )
    quantity: float = Field(
        description="Number of units consumed per month, e.g. 730 for a VM running 24/7 (hours), or 1000000 for 1M function executions"
    )
    label: str = Field(
        default="",
        description="Optional label for this line item, e.g. 'D4s v5 VM - East US' or 'Azure Functions executions'",
    )


def register(mcp):

    @mcp.tool
    async def cost_estimator(
        unit_price: float,
        unit_of_measure: str,
        quantity: float,
        label: str = "",
    ) -> str:
        """Estimate monthly and annual Azure costs from a unit price and usage quantity.
        Takes a unit price (from the Azure Retail Prices API), unit of measure, and monthly quantity.
        Always call this after fetching prices from the azure-pricing skill.
        Returns a formatted cost breakdown with monthly and annual totals."""

        monthly_cost = unit_price * quantity
        annual_cost = monthly_cost * 12
        label_line = f"**{label}**\n" if label else ""

        return (
            f"{label_line}"
            f"Unit price:    ${unit_price:.6f} per {unit_of_measure}\n"
            f"Monthly usage: {quantity:,.2f} {unit_of_measure}(s)\n"
            f"─────────────────────────────────\n"
            f"Monthly cost:  ${monthly_cost:,.4f}\n"
            f"Annual cost:   ${annual_cost:,.4f}\n"
        )
