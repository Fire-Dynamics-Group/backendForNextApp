"""Warehouse smoke layer Word report.

Layout: ``templates/warehouse/skin_single_building.docx`` is the team's report with its
body emptied (cover, TOC, header, footer, styles). ``report_single_building.j2`` is the
prose, one paragraph per line with a style marker, rendered by Jinja. ``blocks/`` holds
the equations and diagram that cannot be written as text. ``builder.DocBuilder`` turns
the rendered text into paragraphs on the skin.
"""
