#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from itertools import islice
from trytond.model import fields, ModelSQL
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.error import UserError
from trytond.const import RECORD_CACHE_SIZE

__all__ = ['Link', 'Journal', 'Account', 'Type', 'TaxCode', 'Tax', 'Rule',
    'RuleLine']
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


class Journal(ModelSQL):
    'Account Company Sync Journal'
    __name__ = 'company.account.sync_journal'
    action = fields.Selection([
            ('create', 'Create'),
            ('write', 'Write'),
            ('delete', 'Delete'),
            ], 'Action')
    record = fields.Reference('Record', selection='get_models')

    @staticmethod
    def get_models():
        pool = Pool()
        Model = pool.get('ir.model')
        Link = pool.get('company.account.link')
        model_names = ['company.account.link'] + Link.get_syncronized_models()
        models = Model.search([
                ('model', 'in', model_names),
                ])
        res = []
        for model in models:
            res.append([model.model, model.name])
        return res

    @classmethod
    def syncronize(cls):
        pool = Pool()
        Lang = pool.get('ir.lang')
        Configuration = pool.get('ir.configuration')
        langs = Lang.search([
                ('translatable', '=', True),
                ('code', '!=', Configuration.get_language()),
            ])
        with Transaction().set_user(0):
            entries = cls.search([])
            latter = []
            for entry in entries:
                try:
                    entry.sync(langs)
                except UserError:
                    #One2Many with parent record still not created
                    latter.append(entry)
            for entry in latter:
                entry.sync(langs)
            if entries:
                cls.delete(entries)

    def sync(self, langs=None):
        pool = Pool()
        Link = pool.get('company.account.link')
        record = self.record
        if self.action == 'delete':
            Target = pool.get(record.model)
            to_delete = Target.search([
                    ('sync_link', '=', record),
                    ])
            if to_delete:
                with Transaction().set_context(sync_companies=False):
                    Target.delete(to_delete)
                    Link.delete([record])
        else:
            record.sync_to_all_companies(langs=langs)


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
    _company_search_field = 'company'

    link_required = fields.Function(fields.Boolean('Link Required'),
        'get_link_required')
    sync_link = fields.Many2One('company.account.link', 'Link',
        states={
            'required': Eval('link_required', False),
            },
        depends=['link_required'])

    @classmethod
    def get_link_required(cls, records, name):
        pool = Pool()
        Config = pool.get('account.configuration')
        config = Config.get_singleton()
        required = False
        if config:
            required = config.sync_companies
        if Transaction().context.get('link_not_required'):
            required = False
        return {}.fromkeys([r.id for r in records], required)

    @classmethod
    def syncronized(cls):
        pool = Pool()
        Config = pool.get('account.configuration')
        config = Config.get_singleton()
        if config:
            return config.sync_companies
        return False

    def companies_to_sync(self):
        pool = Pool()
        Company = pool.get('company.company')
        domain = []
        company_id = self
        for name in self._company_search_field.split('.'):
            company_id = getattr(company_id, name)
            if not company_id:
                break
        if company_id:
            domain = [('id', '!=', company_id)]
        return Company.search(domain)

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
    def _get_target_model(cls, field):
        pool = Pool()
        target = None
        relation = getattr(cls._fields[field], 'relation_name', None)
        if relation:
            #Many2Many fields
            Relation = pool.get(relation)
            target = Relation._fields[cls._fields[field].target].model_name
        else:
            #Many2One and One2Many fields
            target = getattr(cls._fields[field], 'model_name', None)
        return target

    @classmethod
    def convert_values(cls, values, new_company, old_company):
        'Converts al values to the company values'
        pool = Pool()
        Link = pool.get('company.account.link')
        new_values = {}
        for key, value in values.iteritems():
            target = cls._get_target_model(key)
            if value and target and target in Link.get_syncronized_models():
                if isinstance(value, ModelSQL):
                    links = [value.sync_link.id]
                else:
                    links = [v.sync_link.id for v in value]
                Target = pool.get(target)
                with Transaction().set_user(0):
                    new_value = Target.search([
                            ('sync_link', 'in', links),
                            (Target._company_search_field, '=',
                                new_company.id),
                            ])
                if isinstance(value, ModelSQL):
                    value = new_value[0] if new_value else None
                else:
                    value = new_value
            new_values[key] = value
        if hasattr(cls, 'company'):
            new_values['company'] = new_company
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
        if not cls.syncronized():
            return
        links = {}
        for field in cls._syncronize_link_fields():
            links[field] = {}
        with Transaction().set_user(0):
            #TODO: Replace with grouped slice
            count = RECORD_CACHE_SIZE
            for i in xrange(0, len(records), count):
                sub_records = islice(records, i, i + count)
                to_write = {}

                for record in sub_records:
                    link = cls._get_link(record, links)
                    if link not in to_write:
                        to_write[link] = []
                    to_write[link].append(record)
                args = []
                for value, models in to_write.iteritems():
                    args += [models, {'sync_link': value}]
                if args:
                    with Transaction().set_context(sync_companies=False):
                        cls.write(*args)

    @classmethod
    def _get_link(cls, record, links=None):
        '''Returns the current link for the record.
        The record can be an instance or a dict with instance values
        '''
        pool = Pool()
        Link = pool.get('company.account.link')
        if not cls.syncronized():
            return
        if links is None:
            links = {}
        for field in cls._syncronize_link_fields():
            if hasattr(record, field) and getattr(record, field):
                try:
                    link = links[field][getattr(record, field)]
                    break
                except KeyError:
                    linked = cls.search([
                            ('sync_link', '!=', None),
                            (field, '=', getattr(record, field)),
                            ])
                    if linked:
                        link = linked[0].sync_link.id
        else:
            link, = Link.create([{'model': cls.__name__}])
            link = link.id

        for field in cls._syncronize_link_fields():
            if (hasattr(record, field) and
                    getattr(record, field)):
                links[field][getattr(record, field)] = link
        return link

    def sync_to_all_companies(self, langs=None):
        'Syncs this account, to all companies'
        if not self.syncronized():
            return
        if not Transaction().context.get('sync_companies', True):
            return

        for company in self.companies_to_sync():
            self.sync_to_company(company, langs)

    def sync_to_company(self, company, langs=None):
        'Sync this account to the company company'
        pool = Pool()
        Lang = pool.get('ir.lang')
        if langs is None:
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
            if fields_translate:
                for lang in langs:
                    with Transaction().set_context(language=lang.code):
                        data = self.read([self.id],
                            fields_names=fields_translate)[0]
                        translations[lang.code] = data
            with Transaction().set_context(sync_companies=False,
                    company=company.id):
                new_vals = self.convert_values(current_vals, company,
                    getattr(self, 'company', None))
                records = self.search([
                        ('sync_link', '=', self.sync_link),
                        (self._company_search_field, '=', company),
                        ], limit=1)
                if records:
                    record, = records
                else:
                    record = self.__class__()
                for key, value in new_vals.iteritems():
                    old_value = None
                    if hasattr(record, key):
                        old_value = getattr(record, key)
                    if old_value != value:
                        setattr(record, key, value)
                record.save()
                #Copy translations
                for lang_code, data in translations.iteritems():
                    with Transaction().set_context(language=lang_code,
                            fuzzy_translation=False, sync_companies=False):
                        self.write([record], data)

    @classmethod
    def create_journal_entries(cls, records, action):
        pool = Pool()
        Journal = pool.get('company.account.sync_journal')
        if not cls.syncronized():
            return
        if not Transaction().context.get('sync_companies', True):
            return
        to_create = [{'action': action, 'record': str(r)} for r in records]
        Journal.create(to_create)

    @classmethod
    def create(cls, vlist):
        for value in vlist:
            if value.get('sync_link'):
                continue
            link = cls._get_link(value)
            if link:
                value['sync_link'] = link
        records = super(LinkedMixin, cls).create(vlist)
        cls.create_journal_entries(records, 'create')
        return records

    @classmethod
    def write(cls, *args):
        all_records = []
        actions = iter(args)
        for records, _ in zip(actions, actions):
            all_records += records
        super(LinkedMixin, cls).write(*args)
        cls.create_journal_entries(records, 'write')

    @classmethod
    def delete(cls, records):
        links = set([x.sync_link for x in records])
        cls.create_journal_entries(links, 'delete')
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

    @classmethod
    def __setup__(cls):
        super(RuleLine, cls).__setup__()
        cls._company_search_field = 'rule.company'
