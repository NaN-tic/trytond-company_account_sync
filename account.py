#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import fields, ModelSQL
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction

__all__ = ['Link', 'Account', 'Type', 'TaxCode', 'Tax', 'Rule', 'RuleLine']
__metaclass__ = PoolMeta


class Link(ModelSQL):
    'Account Company Link'
    __name__ = 'company.account.link'

    model = fields.Char('Model', required=True)

    @staticmethod
    def get_syncronized_models():
        '''
        Return list of syncronitzed Models

        NOTE: THe models must be sorted in the order of syncronizated, been
        the lastest models the ones that depend on other models.

        '''
        return [
            'account.account.type',
            'account.account',
            'account.tax.code',
            'account.tax.rule',
            'account.tax.rule.line',
            'account.tax',
            ]


class LinkedMixin:
    '''
    Mixin to provide sincronization throw the company.account.link model

    - A new Many2One field to the linked model is added in order to define
    the target model that is the reference for copying new values. This field
    is required when the sync_companies flag is set on configuration.

    -If fields needs to be excluded for syncrontization it can be added to
    the _syncronize_excluded_fields
    '''
    _syncronize_excluded_fields = set(['create_date', 'create_uid',
            'write_date', 'write_uid', 'id', 'company', 'left', 'right',
            'childs'])

    link_required = fields.Function(fields.Boolean('Link Required'),
        'get_link_required')
    sync_link = fields.Many2One('company.account.link', 'Link',
        states={
            'required': Eval('link_required', False),
            },
        depends=['link_required'])

    @classmethod
    def syncronized(cls):
        pool = Pool()
        Config = pool.get('account.configuration')
        config = Config.get_singleton()
        if config:
            return config.sync_companies
        return False

    @classmethod
    def companies_to_sync(cls):
        pool = Pool()
        Company = pool.get('company.company')
        company_id = Transaction().context.get('company')
        return Company.search([('id', '!=', company_id)])

    @classmethod
    def fields_to_sync(cls):
        """
        Returns a tuple with the fields to sync a the fields to convert
        per conmpany
        """
        to_sync = []
        for fname, field in cls._fields.iteritems():
            if (isinstance(field, fields.Function) or
                    fname in cls._syncronize_excluded_fields):
                continue
            to_sync.append(fname)
        return to_sync

    @classmethod
    def convert_values(cls, values, new_company):
        'Converts al values to the company values'
        pool = Pool()
        Link = pool.get('company.account.link')
        new_values = {}
        for key, value in values.iteritems():
            relation = getattr(cls._fields[key], 'relation_name', None)
            if relation:
                #Many2Many fields
                Relation = pool.get(relation)
                target = Relation._fields[cls._fields[key].target].model_name
            else:
                #Many2One and One2Many fields
                target = getattr(cls._fields[key], 'model_name', None)
            if value and target and target in Link.get_syncronized_models():
                if isinstance(value, ModelSQL):
                    links = [value.sync_link.id]
                else:
                    links = [v.sync_link.id for v in value]
                Target = pool.get(target)
                with Transaction().set_user(0):
                    new_value = Target.search([
                            ('sync_link', 'in', links),
                            ('company', '=', new_company.id),
                            ])
                if isinstance(value, ModelSQL):
                    value = new_value[0] if new_value else None
                else:
                    value = new_value
            new_values[key] = value
        new_values['company'] = new_company.id
        return new_values

    @classmethod
    def _syncronize_link_fields(cls):
        '''
        Returns a list of fields that must be used as primary key in
        order to search for the model in other companies
        '''
        return ['template', 'code']

    @classmethod
    def syncronize_link(cls, records):
        '''
        Set's the link for the current record and syncronizes values
        if needed.

        It tries to search for a model in another company with the same
        template or code, if none found, it sets the link to the current
        record, so the record becomes the master record.
        '''
        pool = Pool()
        Link = pool.get('company.account.link')
        if not cls.syncronized():
            return
        to_write = []
        links = {}
        for field in cls._syncronize_link_fields():
            links[field] = {}
        with Transaction().set_user(0):
            for record in records:
                for field in cls._syncronize_link_fields():
                    if hasattr(record, field) and getattr(record, field):
                        try:
                            link = links[field][getattr(record, field)]
                            to_write.extend(([record], {
                                        'sync_link': link
                                        }))
                            break
                        except KeyError:
                            linked = cls.search([
                                    ('sync_link', '!=', None),
                                    (field, '=', getattr(record, field)),
                                    ])
                            if linked:
                                value = {
                                    'sync_link': linked[0].sync_link.id,
                                    }
                                to_write.extend(([record], value))
                                break
                else:
                    link, = Link.create([{'model': cls.__name__}])
                    for field in cls._syncronize_link_fields():
                        if hasattr(record, field) and getattr(record, field):
                            links[field][getattr(record, field)] = link.id
                    to_write.extend(([record], {
                                'sync_link': link.id
                                }))
            if to_write:
                with Transaction().set_context(sync_companies=False):
                    cls.write(*to_write)

    def sync_to_all_companies(self):
        'Syncs this account, to all companies'
        if not self.syncronized():
            return
        if not Transaction().context.get('sync_companies', True):
            return

        for company in self.companies_to_sync():
            self.sync_to_company(company)

    def sync_to_company(self, company):
        'Sync this account to the company company'
        pool = Pool()
        Lang = pool.get('ir.lang')
        langs = Lang.search([
            ('translatable', '=', True),
            ])
        current_vals = {}
        fields_translate = []
        for fname in self.fields_to_sync():
            if (fname in self._fields and
                    getattr(self._fields[fname], 'translate', False)):
                fields_translate.append(fname)
            value = getattr(self, fname)
            key = fname
            current_vals[key] = value

        translations = {}
        with Transaction().set_user(0):
            for lang in langs:
                with Transaction().set_context(language=lang.code):
                    data = self.read([self.id],
                        fields_names=fields_translate)[0]
                    translations[lang.code] = data
            with Transaction().set_context(sync_companies=False,
                    company=company.id):
                new_vals = self.convert_values(current_vals, company)
                records = self.search([
                        ('sync_link', '=', self.sync_link),
                        ('company', '=', company),
                        ], limit=1)
                if records:
                    record, = records
                    for key, value in new_vals.iteritems():
                        setattr(record, key, value)
                    record.save()
                else:
                    record, = self.create([new_vals])
                #Copy translations
                for lang_code, data in translations.iteritems():
                    with Transaction().set_context(language=lang_code,
                            fuzzy_translation=False, sync_companies=False):
                        self.write([record], data)

    @classmethod
    def create(cls, vlist):
        records = super(LinkedMixin, cls).create(vlist)
        to_sync = [r for r in records if not r.sync_link]
        if to_sync:
            cls.syncronize_link(to_sync)
        for record in records:
            record.sync_to_all_companies()
        return records

    @classmethod
    def write(cls, *args):
        all_records = []
        actions = iter(args)
        for records, _ in zip(actions, actions):
            all_records += records
        super(LinkedMixin, cls).write(*args)
        for record in all_records:
            record.sync_to_all_companies()

    @classmethod
    def delete(cls, records):
        transaction = Transaction()
        links = [r.sync_link for r in records]
        if cls.syncronized() and transaction.context.get('sync_companies',
                True):
            with transaction.set_user(0):
                to_delete = cls.search([
                        ('sync_link', 'in', links),
                        ])
                if to_delete:
                    super(LinkedMixin, cls).delete(to_delete)
        super(LinkedMixin, cls).delete(records)

    @classmethod
    def copy(cls, records, defaults=None):
        if not defaults:
            defaults = {}
        defaults.setdefault('sync_link', None)
        return super(LinkedMixin, cls).copy(records, defaults)


class Account(LinkedMixin):
    __name__ = 'account.account'

    @classmethod
    def __setup__(cls):
        super(Account, cls).__setup__()
        cls._syncronize_excluded_fields |= set(['deferrals'])


class Type(LinkedMixin):
    __name__ = 'account.account.type'


class TaxCode(LinkedMixin):
    __name__ = 'account.tax.code'


class Tax(LinkedMixin):
    __name__ = 'account.tax'


class Rule(LinkedMixin):
    __name__ = 'account.tax.rule'


class RuleLine(LinkedMixin):
    __name__ = 'account.tax.rule.line'
