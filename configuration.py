#The COPYRIGHT file at the top level of this repository contains the full
#copyright notices and license terms.
from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['Configuration']
__metaclass__ = PoolMeta


class Configuration:
    __name__ = 'account.configuration'
    sync_companies = fields.Boolean('Sync Companies', help='If marked all the '
            'accounts changes will be replicated to all the companies')

    @staticmethod
    def default_sync_companies():
        return False

    @classmethod
    def syncronize_models(cls):
        """
        This will sync the current values of the company to all companies. It
        will also ensure that all the values of the current companies are
        saved to all companies.
        """
        pool = Pool()
        Link = pool.get('company.account.link')
        config = cls.get_singleton()
        if not config.sync_companies:
            return

        to_sync = []
        #First ensure that all the links are set.
        for model in Link.get_syncronized_models():
            Model = pool.get(model)
            with Transaction().set_user(0):
                records = Model.search([('sync_link', '=', None)])
            Model.syncronize_link(records)
            to_sync.extend(records)
        #Sync all the records to all the companies
        for record in to_sync:
            record.sync_to_all_companies()

    @classmethod
    def create(cls, vlist):
        configs = super(Configuration, cls).create(vlist)
        cls.syncronize_models()
        return configs

    @classmethod
    def write(cls, configurations, value):
        super(Configuration, cls).write(configurations, value)
        if value.get('sync_companies'):
            cls.syncronize_models()
