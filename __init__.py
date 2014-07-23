# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .configuration import *
from .account import *


def register():
    Pool.register(
        Link,
        Configuration,
        Account,
        Type,
        TaxCode,
        Tax,
        Rule,
        RuleLine,
        module='company_account_sync', type_='model')
