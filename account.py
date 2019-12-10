# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
import logging
from trytond.model import fields, ModelView
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.wizard import Wizard, StateView, StateTransition, Button
from trytond.i18n import gettext
from trytond.exceptions import UserError

logger = logging.getLogger(__name__)

__all__ = ['TypeTemplate', 'AccountTemplate', 'TaxCodeTemplate',
    'TaxTemplate', 'TaxRuleTemplate', 'TaxRuleLineTemplate', 'SyncronizeChartStart',
    'SyncronizeChartSucceed', 'SyncronizeChart']


class CompanySyncMixin(metaclass=PoolMeta):
    _syncronized_field = ''

    def get_syncronized_company_value(self, company):
        if not company.intercompany_user:
            raise UserError(gettext(
                'company_account_sync.missing_intercompany_user',
                company=company.party.name))

        with Transaction().set_user(company.intercompany_user.id), \
                Transaction().set_context(company=company.id,
                _check_access=False):
            instance = self.__class__(self)
            for value in getattr(instance, instance._syncronized_field):
                if value.company == company:
                    return value
            return


class TypeTemplate(CompanySyncMixin):
    __name__ = 'account.account.type.template'
    _syncronized_field = 'types'
    types = fields.One2Many('account.account.type', 'template', 'Types')


class AccountTemplate(CompanySyncMixin):
    __name__ = 'account.account.template'
    _syncronized_field = 'accounts'
    accounts = fields.One2Many('account.account', 'template', 'Accounts')


class TaxCodeTemplate(CompanySyncMixin):
    __name__ = 'account.tax.code.template'
    _syncronized_field = 'tax_codes'
    tax_codes = fields.One2Many('account.tax.code', 'template', 'Tax Codes')


class TaxTemplate(CompanySyncMixin):
    __name__ = 'account.tax.template'
    _syncronized_field = 'taxes'
    taxes = fields.One2Many('account.tax', 'template', 'Taxes')


class TaxRuleTemplate(CompanySyncMixin):
    __name__ = 'account.tax.rule.template'
    _syncronized_field = 'tax_rules'
    tax_rules = fields.One2Many('account.tax.rule', 'template', 'Tax Rules')


class TaxRuleLineTemplate(CompanySyncMixin):
    __name__ = 'account.tax.rule.line.template'
    _syncronized_field = 'tax_rule_lines'
    tax_rule_lines = fields.One2Many('account.tax.rule.line', 'template',
        'Tax Rule Lines')


class SyncronizeChartStart(ModelView):
    'Syncornize Account Chart'
    __name__ = 'account.chart.syncronize.start'
    account_template = fields.Many2One('account.account.template',
        'Account Template', required=True,
        domain=[
            ('parent', '=', None),
            ])
    companies = fields.Many2Many('company.company', None, None, 'Companies',
        required=True)

    @classmethod
    def default_account_template(cls):
        pool = Pool()
        Template = pool.get('account.account.template')
        templates = Template.search(cls.account_template.domain)
        if len(templates) == 1:
            return templates[0].id

    @staticmethod
    def default_companies():
        pool = Pool()
        Company = pool.get('company.company')
        return [x.id for x in Company.search([])]


class SyncronizeChartSucceed(ModelView):
    'Syncronize Account Chart Succeed'
    __name__ = 'account.chart.syncronize.succeed'


class SyncronizeChart(Wizard):
    'Syncronize Chart'
    __name__ = 'account.chart.syncronize'
    start = StateView('account.chart.syncronize.start',
        'company_account_sync.syncronize_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Ok', 'syncronize', 'tryton-ok', default=True),
            ])
    syncronize = StateTransition()
    succeed = StateView('account.chart.syncronize.succeed',
        'company_account_sync.syncronize_succeed_view_form', [
            Button('Ok', 'end', 'tryton-ok', default=True),
            ])

    @classmethod
    def __setup__(cls):
        super(SyncronizeChart, cls).__setup__()

    def transition_syncronize(self):
        pool = Pool()
        Account = pool.get('account.account')
        CreateChart = pool.get('account.create_chart', type='wizard')
        UpdateChart = pool.get('account.update_chart', type='wizard')

        template = self.start.account_template
        transaction = Transaction()

        def root_childs(template, templates=[]):
            templates.append(template)

            for child in template.childs:
                root_childs(child, templates)
            return templates

        codes = []
        for tpl in root_childs(template):
            vals = tpl._get_account_value()
            codes.append(vals['code'])

        # check accounts that have same code before upgrade account chart
        for company in self.start.companies:
            with transaction.set_context(company=company.id,
                    _check_access=False):
                accounts = Account.search([
                    ('code', 'in', codes),
                    ('company', '=', company.id),
                    ('template', '=', None),
                    ])
                if accounts:
                    codes = ','.join([a.code for a in accounts])
                    raise UserError(gettext(
                        'company_account_sync.accounts_same_code',
                        template=codes
                    ))

        for company in self.start.companies:
            def set_defaults(form):
                field_names = set(form.__class__._fields)
                for key, value in form.default_get(field_names).items():
                    setattr(form, key, value)

            if not company.intercompany_user:
                raise UserError(gettext(
                    'company_account_sync.missing_intercompany_user',
                    company=company.party.name))

            with Transaction().set_user(company.intercompany_user.id), \
                    Transaction().set_context(company=company.id,
                    _check_access=False):
                logger.info('Syncronizing company %s' % company.rec_name)
                roots = Account.search([
                        ('company', '=', company.id),
                        ('template', '=', template.id),
                        ])
                if roots:
                    logger.info('Updating existing chart')
                    root, = roots

                    session_id, _, _ = UpdateChart.create()
                    update = UpdateChart(session_id)
                    set_defaults(update.start)
                    update.start.account = root
                    update.transition_update()
                    Account._rebuild_tree('parent', None, 0)
                    update.delete(session_id)
                else:
                    logger.info('No Chart created %s' % company.rec_name)

                #     logger.info('Creating new chart')
                #     session_id, _, _ = CreateChart.create()
                #     create = CreateChart(session_id)
                #     create.account.company = company
                #     create.account.account_template = template
                #     set_defaults(create.account)
                #     with transaction.set_user(0):
                #         create.transition_create_account()
                #     receivables = Account.search([
                #             ('kind', '=', 'receivable'),
                #             ('company', '=', company.id),
                #             ], limit=1)
                #     payables = Account.search([
                #             ('kind', '=', 'payable'),
                #             ('company', '=', company.id),
                #             ], limit=1)
                #     if receivables and payables:
                #         receivable, = receivables
                #         payable, = payables
                #         create.properties.company = company
                #         create.properties.account_receivable = receivable
                #         create.properties.account_payable = payable
                #         with transaction.set_user(0):
                #             create.transition_create_properties()
                #     create.delete(session_id)
                logger.info('Finished syncronizing company %s' %
                    company.rec_name)

        return 'succeed'
