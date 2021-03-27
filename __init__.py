# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from . import account


def register():
    Pool.register(
        account.TypeTemplate,
        account.AccountTemplate,
        account.TaxCodeTemplate,
        account.TaxTemplate,
        account.TaxRuleTemplate,
        account.TaxRuleLineTemplate,
        account.SyncronizeChartStart,
        account.SyncronizeChartSucceed,
        module='company_account_sync', type_='model')
    Pool.register(
        account.SyncronizeChart,
        module='company_account_sync', type_='wizard')
