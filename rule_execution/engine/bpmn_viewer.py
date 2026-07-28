def export_to_bpmn_xml(engine, start_node_id: str | int, output_file: str = "rule_engine.bpmn"):
    """
    Parses the RuleExecutionEngine configuration and generates a STRICTLY VALID BPMN 2.0 XML file.
    Includes the BPMNDI layer so modelers (like Camunda) accept the file and can auto-layout it.
    """
    start_node_id = str(start_node_id)
    
    # 1. Standard BPMN Boilerplate with all required XML Namespaces
    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<bpmn:definitions ',
        '  xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" ',
        '  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI" ',
        '  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC" ',
        '  xmlns:di="http://www.omg.org/spec/DD/20100524/DI" ',
        '  id="Definitions_1" targetNamespace="http://bpmn.io/schema/bpmn">',
        '  <bpmn:process id="Process_RuleEngine" isExecutable="true">',
        
        # Start and End Events
        '    <bpmn:startEvent id="StartEvent_1" name="Start" />',
        f'    <bpmn:sequenceFlow id="Flow_Start" sourceRef="StartEvent_1" targetRef="Activity_{start_node_id}" />',
        '    <bpmn:endEvent id="EndEvent_1" name="End" />'
    ]

    # 2. Generate Nodes and Gateways
    for node_id, config in engine.nodes_config.items():
        node_type = config.get("type", "Custom")
        
        # Map Node Type to BPMN Task Type
        if node_type == "Deterministic":
            task_tag = "businessRuleTask"
        elif node_type == "GenAI":
            task_tag = "serviceTask"
        else:
            task_tag = "scriptTask"

        xml_lines.append(f'    <bpmn:{task_tag} id="Activity_{node_id}" name="{node_type} Node ({node_id})" />')
        
        # Exclusive Gateway for Pass/Fail/Error routing
        gw_id = f"Gateway_Status_{node_id}"
        xml_lines.append(f'    <bpmn:exclusiveGateway id="{gw_id}" name="Status ({node_id})" />')
        xml_lines.append(f'    <bpmn:sequenceFlow id="Flow_{node_id}_out" sourceRef="Activity_{node_id}" targetRef="{gw_id}" />')

        # 3. Generate Conditional & Parallel Sequence Flows
        for route in ["onPass", "onFail", "onError"]:
            targets = config.get(route, "END")
            targets = [targets] if isinstance(targets, str) else targets 
            
            if len(targets) == 1:
                # Direct Route
                target_ref = "EndEvent_1" if targets[0] == "END" else f"Activity_{targets[0]}"
                xml_lines.append(f'    <bpmn:sequenceFlow id="Flow_{node_id}_{route}" name="{route}" sourceRef="{gw_id}" targetRef="{target_ref}" />')
            else:
                # Parallel Route Fan-out -> Requires a Parallel Gateway
                fork_id = f"Gateway_Fork_{node_id}_{route}"
                xml_lines.append(f'    <bpmn:parallelGateway id="{fork_id}" name="Parallel Fan-out" />')
                xml_lines.append(f'    <bpmn:sequenceFlow id="Flow_{node_id}_{route}_to_fork" name="{route}" sourceRef="{gw_id}" targetRef="{fork_id}" />')
                
                for idx, t in enumerate(targets):
                    target_ref = "EndEvent_1" if t == "END" else f"Activity_{t}"
                    xml_lines.append(f'    <bpmn:sequenceFlow id="Flow_fork_{node_id}_{route}_to_{t}_{idx}" sourceRef="{fork_id}" targetRef="{target_ref}" />')

    xml_lines.append('  </bpmn:process>')

    # 4. Critical Fix: Inject BPMNDI (Diagram Interchange) block
    # Even if empty, strictly valid parsers require this wrapper to load the file
    xml_lines.append('  <bpmndi:BPMNDI>')
    xml_lines.append('    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_RuleEngine">')
    xml_lines.append('      <!-- Modeler will generate coordinates upon auto-layout -->')
    xml_lines.append('    </bpmndi:BPMNPlane>')
    xml_lines.append('  </bpmndi:BPMNDI>')
    
    xml_lines.append('</bpmn:definitions>')
    
    xml_content = "\n".join(xml_lines)
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(xml_content)
        
    print(f"✅ BPMN XML successfully exported to {output_file}")
    return xml_content
