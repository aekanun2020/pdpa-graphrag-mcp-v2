import json,urllib.request,sys
def post(payload):
    h={"Content-Type":"application/json","Accept":"application/json, text/event-stream"}
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8100/mcp",data=json.dumps(payload).encode(),headers=h),timeout=30)
    return json.loads(r.read().decode())
def call(name,args):
    res=post({"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":name,"arguments":args}})["result"]
    return res
for name,args in [("get_section_text",{"section_id":"sec_26"}),("get_section_text",{"section_id":"sec_999"}),("get_section_text",{"section_id":"26"}),("get_penalty",{"section_id":"sec_26"}),("get_penalty",{"section_id":"sec_84"}),("get_related_sections",{"section_id":"sec_37"}),("get_pdpa_summary",{})]:
    r=call(name,args)
    t=r["content"][0]["text"]
    print("==",name,args,"isError",r.get("isError"),"blocks",len(r["content"]),"keys",[k for k in r if k!="content"],"len",len(t))
    print(t[:700])
