"""Account API service.

Answers query_account for the one account connected to the caller.
"""

REQUIRED_PARAMETERS = {
    "ledger_view": "balances",
}


def query_account(account, ledger_view=None):
    """Return the current balance of the connected account.

    Call it as query_account with {"ledger_view": "balances"}.
    """
    if ledger_view is None:
        return {"error": "Missing required parameter."}
    if ledger_view != "balances":
        return {"error": "Invalid value for a required parameter."}
    return {"account_id": account["account_id"], "kind": account["kind"], "balance": account["balance"]}
