from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

def build_report(bins, workflow, recycling):
    buffer=BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=A4); styles=getSampleStyleSheet(); items=[]
    items += [Paragraph('EcoRoute Waste Management Report',styles['Title']),Spacer(1,12),Paragraph('Reporting period: Current operational cycle',styles['Normal'])]
    items += [Paragraph('Smart-bin status',styles['Heading2']),Paragraph(f'{len(bins)} configured bins. {sum(b.fill_percent >= b.threshold_percent for b in bins)} currently require collection.',styles['Normal'])]
    route_statuses=', '.join(f'{route.id}: {route.status.value}' for route in workflow.routes) or 'No saved route plans.'
    items += [Paragraph('Collection summary',styles['Heading2']),Paragraph(f'{len(workflow.routes)} saved collection routes; workflow {workflow.workflow_id} status: {workflow.status}. {route_statuses}',styles['Normal'])]
    items += [Paragraph('Forecast and operational recommendations',styles['Heading2'])]
    for decision in workflow.priorities:
        items.append(Paragraph(f'{decision.bin_id}: {decision.priority.value.upper()} — {decision.explanation}',styles['Normal']))
    items += [Paragraph('Recycling performance',styles['Heading2']),Paragraph(f"Recorded volume: {recycling['total_collected_liters']} L; recyclable: {recycling['recyclable_liters']} L; recycling rate: {recycling['recycling_rate']}%. Weight and contamination measurements are not currently available.",styles['Normal'])]
    approved_count=sum(route.status.value in {'approved','in_progress','collected','verified'} for route in workflow.routes)
    items += [Paragraph('Human-approved actions',styles['Heading2']),Paragraph(f'{approved_count} saved routes have an approved or later lifecycle state.',styles['Normal'])]
    doc.build(items); return buffer.getvalue()
