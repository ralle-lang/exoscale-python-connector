"""Per-asset-type resource clients.

Each module here exposes one ``*Client`` class (subclass of
:class:`exoscale_connector.resources._base.ResourceClient`) and its pydantic
model(s). Import the specific client you need, e.g.::

    from exoscale_connector.resources.security_group import SecurityGroupClient
"""
