# El presupuesto de AWS (D12): un correo cuando el gasto previsto del mes supera en un 20 %
# el coste estimado del plan. Vigila toda la cuenta, así que solo lo tiene producción: avisa
# también de una preproducción que no se destruyó.
resource "aws_budgets_budget" "monthly" {
  count = local.production ? 1 : 0

  name         = "myplaylist-mensual"
  budget_type  = "COST"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 120
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
