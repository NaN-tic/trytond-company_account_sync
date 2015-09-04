# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .account import *


def register():
    Pool.register(
        SyncronizeChartStart,
        SyncronizeChartSucceed,
        module='company_account_sync', type_='model')
    Pool.register(
        SyncronizeChart,
        module='company_account_sync', type_='wizard')
