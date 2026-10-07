"""MPSA_Voice_Main - spec for flowkit (MPSA-CC-LLD-VOICE-001 v0.9, see MPSA.md).

Build:  python3 .claude/skills/wxcc-flow-builder/scripts/flowkit.py build \
          .claude/skills/wxcc-flow-builder/examples/MPSA.flow.py -o build/MPSA_Voice_Main.flowv2.json
"""
# --- Tenant IDs (MPSA.md section 4). PLACEHOLDERS until the MPSA entities exist in the tenant. ---
Q_GENERAL = "d0f5de68-06ba-49dc-930b-ccd5f3de101e"   # Queue-1   -> Q_MPSA_General_Enquiries
Q_CASE    = "c811d07d-872b-4956-ae93-c31ba03f1a2a"   # CiscoTest -> Q_MPSA_Case_Enquiries
BH_ID     = "22e53e68-7dd1-447d-800a-9c638eba9985"   # OLD_BH_MPSA_Voice -> BH_MPSA_Voice
HOLD_MUSIC = "defaultmusic_on_hold.wav"              # -> MPSA_Hold_Music.wav
VA_NAME   = "MPSA Citizen Assistant"
# HTTP nodes are connector-based and left UNCONFIGURED (no connectorId) by customer decision 2026-10-07.
# The admin creates the connectors in Control Hub and selects them in each node.
ID_CONNECTOR_HINT = ("MANUAL: select Control Hub HTTP connector for the identity service "
                     "(base URL https://identity-mock.example.org/api/v1, header x-api-key as secure credential)")
CONNECT_CONNECTOR_HINT = ("MANUAL: select Control Hub HTTP connector for Webex Connect "
                          "(base URL https://connect.example.org/webhook)")
OVERFLOW_EWT_SECONDS = 600

P = {
 "P01": "{{Global_MPSA_EmergencyMessage}}",
 "P02": "Thank you for calling Meridian Public Services. Our phone lines are open Monday to Friday from 8 a.m. to 5 p.m. You can chat with us on our website until 8 p.m., message our virtual assistant at any time, or find your case details in the online portal. Goodbye.",
 "P03": "Thank you for calling Meridian Public Services. Our offices are closed today for a public holiday. You can use our online portal or virtual assistant at any time. Goodbye.",
 "P04": "Thank you for calling Meridian Public Services. Our phone lines are temporarily closed. Please try again later or visit our website for the latest information. Goodbye.",
 "P05": "Welcome to Meridian Public Services. You are speaking with our virtual assistant, an automated AI service. This call may be recorded and transcribed for quality and training purposes.",
 "P10": "To protect your personal information, I need to verify your identity first. We will send a one-time code by text message to the mobile number registered in your file.",
 "P11": "Please enter your eight-digit citizen reference number, followed by the hash key.",
 "P12": "We could not find that reference number. I will connect you with an employee who can help you further.",
 "P13": "We have sent a six-digit code to your mobile number {{OTP_Destination}}. Please enter the code now.",
 "P14": "That code is not correct. Please try again.",
 "P15": "We could not verify your identity. I will connect you with an employee for general assistance.",
 "P16": "Verification is not available at the moment. I will connect you with an employee.",
 "P17": "Thank you, your identity has been confirmed. I am connecting you with an employee who can see your case.",
 "P20": "You are number {{QueuePosition}} in the queue. The expected waiting time is about {{EWT_Minutes}} minutes.",
 "P21": "Thank you for your patience. Many answers are also available in our online portal.",
 "P22": "The waiting time is currently more than 10 minutes. To receive a callback when it is your turn, press 1. To receive a chat link by text message, press 2. To keep waiting, press 3.",
 "P23": "Thank you. We will call you back on this number when an employee is available. Goodbye.",
 "P24": "We have sent you a text message with a link to our chat. Goodbye.",
 "P25": "We could not send the text message. Please stay on the line.",
 "P30": "We are experiencing a technical issue. Please hold while we connect you with an employee.",
}

f = Flow("MPSA_Voice_Main", "MPSA Citizen Contact Centre inbound voice flow (MPSA-CC-LLD-VOICE-001 v0.9)")

# ---------------- variables (MPSA.md section 5) ----------------
f.var("CallerANI", "STRING", cad=True, label="Caller number", reportable=True, desc="Caller ANI (F02)")
f.var("VA_EscalationReason", "STRING", cad=True, label="Escalation reason", reportable=True, desc="AI Agent escalation_reason")
f.var("VA_Summary", "STRING", cad=True, label="Assistant summary", desc="AI Agent conversation_summary")
f.secure_var("CitizenRef", desc="Raw citizen ref (F11) - cleared at F18")
f.secure_var("OTP_TransactionId", desc="$.transactionId")
f.var("OTP_Destination", "STRING", desc="$.destinationMasked")
f.var("OTP_Found", "BOOLEAN", False, desc="$.found")
f.secure_var("OTP_Input", desc="Raw OTP (F14) - cleared at F18")
f.var("OTP_Verified", "BOOLEAN", False, desc="$.verified")
f.var("AuthAttempts", "INTEGER", 0, reportable=True, desc="OTP attempt counter")
f.var("AuthStatus", "STRING", "Not verified", cad=True, label="Identity status", reportable=True, desc="Identity status")
f.var("CitizenRefMasked", "STRING", cad=True, label="Citizen ref", desc="$.citizen.refMasked")
f.var("CitizenFirstName", "STRING", cad=True, label="First name", desc="$.citizen.firstName")
f.var("CitizenLastName", "STRING", cad=True, label="Last name", desc="$.citizen.lastName")
f.var("CaseRef", "STRING", cad=True, label="Case reference", desc="$.case.ref")
f.var("CaseType", "STRING", cad=True, label="Case type", reportable=True, desc="$.case.type")
f.var("CaseStatus", "STRING", cad=True, label="Case status", desc="$.case.status")
f.var("QueuePosition", "INTEGER", 0, desc="Get Queue Info PIQ")
f.var("EWT_Seconds", "INTEGER", 0, desc="Get Queue Info EWT in seconds")
f.var("EWT_Minutes", "INTEGER", 0, desc="ceil(EWT_Seconds/60)")
f.var("OverflowOffered", "BOOLEAN", False, reportable=True, desc="Overflow offered once")
f.var("RefAttempts", "INTEGER", 0, desc="Helper: F11 retry counter (2 retries)")
f.var("QueueLoopCount", "INTEGER", 0, desc="Helper: F23 loop counter (P21 every 3rd loop)")
f.var("CurrentQueueId", "STRING", Q_GENERAL, desc="Helper: queue the contact is in (F21/F25)")

def jp(src, path):
    return "{{ " + src + " | jsonPath('" + path + "') }}"

def play(name, pid, desc, **kw):
    return f.play(name, pid, P[pid], desc, **kw)

# ---------------- 4.1 Entry and opening hours ----------------
f.start("NewPhoneContact", "F01 - Inbound voice contact from EP_MPSA_Voice")
f.setv("F02_InitVars", "F02 - Initialise caller and state variables",
       ("CallerANI", "STRING", "{{NewPhoneContact.ANI}}"), ("AuthStatus", "STRING", "Not verified"),
       ("AuthAttempts", "INTEGER", "0"), ("OverflowOffered", "BOOLEAN", "false"))
f.cond("F03_EmergencyCheck", "{{ Global_MPSA_EmergencyActive == true }}", "F03 - Emergency announcement active?")
play("F04_EmergencyMsg", "P01", "F04 - Supervisor emergency announcement (P01)")
f.business_hours("F05_BusinessHours", BH_ID, "F05 - BH_MPSA_Voice with HL_MPSA_Public_Holidays and OV_MPSA_Adhoc_Closure")
play("F06a_ClosedMsg", "P02", "F06 - Outside opening hours (P02)")
play("F06b_HolidayMsg", "P03", "F06 - Public holiday (P03)")
play("F06c_OverrideMsg", "P04", "F06 - Ad-hoc closure override (P04)")
f.disconnect("F06_Disconnect", "F06 - Disconnect after closed prompt")

f.edge("NewPhoneContact", "F02_InitVars", "out")
f.edge("F02_InitVars", "F03_EmergencyCheck", "out", "error")
f.edge("F03_EmergencyCheck", "F04_EmergencyMsg", "true")
f.edge("F03_EmergencyCheck", "F05_BusinessHours", "false", "error")
f.edge("F04_EmergencyMsg", "F05_BusinessHours", "default", "error")
f.edge("F05_BusinessHours", "F07_Welcome", "workingHours")
f.edge("F05_BusinessHours", "F06b_HolidayMsg", "holidays")
f.edge("F05_BusinessHours", "F06c_OverrideMsg", "override")
f.edge("F05_BusinessHours", "F06a_ClosedMsg", "default", "error")
for n in ("F06a_ClosedMsg", "F06b_HolidayMsg", "F06c_OverrideMsg"):
    f.edge(n, "F06_Disconnect", "default", "error")

# ---------------- 4.2 Welcome and AI Agent ----------------
play("F07_Welcome", "P05", "F07 - Welcome, AI transparency and recording notice (MAND-01/02, not interruptible)", interruptible=False)
f.virtual_agent("F08_AIAgent", VA_NAME, "F08 - AI Agent MPSA Citizen Assistant (anonymous FAQ, general information only)")
f.disconnect("F08_Disconnect", "F08 - Handled by AI Agent, end call")
f.setv("F08a_MapVaOutputs", "F08 - Map AI Agent outputs escalation_reason and conversation_summary",
       ("VA_EscalationReason", "STRING", jp("F08_AIAgent.MetaData", "$.escalation_reason")),
       ("VA_Summary", "STRING", jp("F08_AIAgent.MetaData", "$.conversation_summary")))
f.cond("F09_EscalationCase", '{{ VA_EscalationReason == "auth_required" }}',
       "F09 - auth_required -> OTP verification; agent_requested/unresolved/default -> general queue")

f.edge("F07_Welcome", "F08_AIAgent", "default", "error")
f.edge("F08_AIAgent", "F08_Disconnect", "ENDED")
f.edge("F08_AIAgent", "F08a_MapVaOutputs", "ESCALATE")
f.edge("F08_AIAgent", "F20_QueueGeneral", "error")
f.edge("F08a_MapVaOutputs", "F09_EscalationCase", "out", "error")
f.edge("F09_EscalationCase", "F10_VerifyIntro", "true")
f.edge("F09_EscalationCase", "F20_QueueGeneral", "false", "error")

# ---------------- 4.3 Identity verification (OTP) ----------------
play("F10_VerifyIntro", "P10", "F10 - Verification introduction (P10)")
f.collect("F11_CollectRef", "P11", P["P11"], "F11 - Collect 8-digit citizen reference, 8 s timeout",
          min_digits=8, max_digits=8, timeout=8)
f.setv("F11a_StoreRef", "F11 - Store citizen reference (secure, non-reportable)",
       ("CitizenRef", "STRING", "{{F11_CollectRef.DigitsEntered}}"))
f.setv("F11r_IncRefAttempts", "F11 - Count failed reference entry", ("RefAttempts", "INTEGER", "{{ RefAttempts + 1 }}"))
f.cond("F11s_CheckRefRetry", "{{ RefAttempts <= 2 }}", "F11 - Up to 2 retries, then general queue unverified")
f.http("F12_SendOtp", "/otp/send",
       "F12 - POST /otp/send (OTP to registered mobile only); parses found/transactionId/destinationMasked. "
       + ID_CONNECTOR_HINT,
       body='{ "citizenRef": "{{CitizenRef}}", "channel": "sms", "callerAni": "{{CallerANI}}" }',
       parse={"OTP_Found": "$.found", "OTP_TransactionId": "$.transactionId",
              "OTP_Destination": "$.destinationMasked"})
play("F12e_VerifyUnavailable", "P16", "F12/F15 - Identity service unavailable (P16)")
f.cond("F13_CheckFound", "{{ OTP_Found == true }}", "F13 - Citizen reference found?")
play("F13f_RefNotFound", "P12", "F13 - Reference not found (P12)")
f.collect("F14_CollectOtp", "P13", P["P13"], "F14 - Collect 6-digit OTP, 30 s timeout",
          min_digits=6, max_digits=6, timeout=30)
f.setv("F14a_StoreOtp", "F14 - Store OTP input (secure, non-reportable)",
       ("OTP_Input", "STRING", "{{F14_CollectOtp.DigitsEntered}}"))
f.http("F15_VerifyOtp", "/otp/verify",
       "F15 - POST /otp/verify; parses verified + citizen/case fields (present only on 200 verified). "
       + ID_CONNECTOR_HINT,
       body='{ "transactionId": "{{OTP_TransactionId}}", "code": "{{OTP_Input}}" }',
       parse={"OTP_Verified": "$.verified", "CitizenRefMasked": "$.citizen.refMasked",
              "CitizenFirstName": "$.citizen.firstName", "CitizenLastName": "$.citizen.lastName",
              "CaseRef": "$.case.ref", "CaseType": "$.case.type", "CaseStatus": "$.case.status"})
f.cond("F16_CheckVerified", "{{ OTP_Verified == true }}", "F16 - OTP verified?")
f.setv("F17a_IncAttempts", "F17 - Increment OTP attempts", ("AuthAttempts", "INTEGER", "{{ AuthAttempts + 1 }}"))
f.cond("F17b_CheckAttempts", "{{ AuthAttempts < 3 }}", "F17 - Fewer than 3 attempts?")
play("F17c_RetryMsg", "P14", "F17 - Wrong code, retry (P14)")
play("F17d_FailedMsg", "P15", "F17 - Verification failed (P15)")
f.setv("F18_SetVerified", "F18 - Mark verified and purge raw reference and OTP (MAND-05)",
       ("AuthStatus", "STRING", "Verified"), ("CitizenRef", "STRING", "''"), ("OTP_Input", "STRING", "''"))
play("F18b_VerifiedMsg", "P17", "F18 - Identity confirmed (P17)")

f.edge("F10_VerifyIntro", "F11_CollectRef", "default", "error")
f.edge("F11_CollectRef", "F11a_StoreRef", "")
f.edge("F11_CollectRef", "F11r_IncRefAttempts", "timeout", "invalid")
f.edge("F11_CollectRef", "F20_QueueGeneral", "error")
f.edge("F11r_IncRefAttempts", "F11s_CheckRefRetry", "out", "error")
f.edge("F11s_CheckRefRetry", "F11_CollectRef", "true")
f.edge("F11s_CheckRefRetry", "F20_QueueGeneral", "false", "error")
f.edge("F11a_StoreRef", "F12_SendOtp", "out")
f.edge("F11a_StoreRef", "F20_QueueGeneral", "error")
f.edge("F12_SendOtp", "F13_CheckFound", "default")
f.edge("F12_SendOtp", "F12e_VerifyUnavailable", "error")
f.edge("F12e_VerifyUnavailable", "F20_QueueGeneral", "default", "error")
f.edge("F13_CheckFound", "F14_CollectOtp", "true")
f.edge("F13_CheckFound", "F13f_RefNotFound", "false")
f.edge("F13_CheckFound", "F12e_VerifyUnavailable", "error")
f.edge("F13f_RefNotFound", "F20_QueueGeneral", "default", "error")
f.edge("F14_CollectOtp", "F14a_StoreOtp", "")
f.edge("F14_CollectOtp", "F17a_IncAttempts", "timeout", "invalid", "error")
f.edge("F14a_StoreOtp", "F15_VerifyOtp", "out")
f.edge("F14a_StoreOtp", "F17a_IncAttempts", "error")
f.edge("F15_VerifyOtp", "F16_CheckVerified", "default")
f.edge("F15_VerifyOtp", "F12e_VerifyUnavailable", "error")
f.edge("F16_CheckVerified", "F18_SetVerified", "true")
f.edge("F16_CheckVerified", "F17a_IncAttempts", "false", "error")
f.edge("F17a_IncAttempts", "F17b_CheckAttempts", "out", "error")
f.edge("F17b_CheckAttempts", "F17c_RetryMsg", "true")
f.edge("F17b_CheckAttempts", "F17d_FailedMsg", "false", "error")
f.edge("F17c_RetryMsg", "F14_CollectOtp", "default", "error")
f.edge("F17d_FailedMsg", "F20_QueueGeneral", "default", "error")
f.edge("F18_SetVerified", "F18b_VerifiedMsg", "out", "error")
f.edge("F18b_VerifiedMsg", "F19a_SetCaseQueue", "default", "error")

# ---------------- 4.4 Queueing, wait time and overflow ----------------
f.setv("F19a_SetCaseQueue", "F19 - Remember current queue (case)", ("CurrentQueueId", "STRING", Q_CASE))
f.queue("F19_QueueCase", Q_CASE, "Q_MPSA_Case_Enquiries (placeholder: CiscoTest)",
        "F19 - Queue verified caller to Q_MPSA_Case_Enquiries (skills Case_Handling >= 5)")
f.setv("F20a_SetGeneralQueue", "F20 - Remember current queue (general)", ("CurrentQueueId", "STRING", Q_GENERAL))
f.queue("F20_QueueGeneral", Q_GENERAL, "Q_MPSA_General_Enquiries (placeholder: Queue-1)",
        "F20 - Queue to Q_MPSA_General_Enquiries (unverified / general)")
# Get Queue Info needs a static queue ID (Flow Designer blanks a variable) -> one lookup per queue.
f.cond("F21_WhichQueue", '{{ CurrentQueueId == "%s" }}' % Q_CASE, "F21 - Caller in case queue? (selects queue lookup)")
for sfx, qid, qlabel in (("c", Q_CASE, "Q_MPSA_Case_Enquiries"), ("g", Q_GENERAL, "Q_MPSA_General_Enquiries")):
    lk = f"F21{sfx}_GetQueueInfo"
    f.queue_lookup(lk, qid, f"F21 - Position and EWT in {qlabel}")
    f.setv(f"F21{sfx}b_StoreQueueInfo", "F21 - Store PIQ and EWT; EWT_Minutes = ceil(EWT_Seconds / 60)",
           ("QueuePosition", "INTEGER", "{{%s.PIQ}}" % lk),
           ("EWT_Seconds", "INTEGER", "{{ %s.EWT / 1000 }}" % lk),
           ("EWT_Minutes", "INTEGER", "{{ (%s.EWT / 1000 + 59) / 60 }}" % lk))
f.cond("F22_CheckOverflow", "{{ EWT_Seconds > %d and OverflowOffered == false }}" % OVERFLOW_EWT_SECONDS,
       "F22 - EWT over 10 minutes and overflow not yet offered?")
f.setv("F23a_IncLoop", "F23 - Count queue loop", ("QueueLoopCount", "INTEGER", "{{ QueueLoopCount + 1 }}"))
play("F23_WaitMsg", "P20", "F23 - Position and wait time (P20)")
f.cond("F23b_Every3rd", "{{ (QueueLoopCount % 3) == 0 }}", "F23 - Every 3rd loop play P21")
play("F23c_PatienceMsg", "P21", "F23 - Patience message (P21)")
f.music("F23d_HoldMusic", "F23 - Hold music 45 s (MPSA_Hold_Music.wav)", prompt=HOLD_MUSIC, seconds=45)
f.setv("F24a_SetOffered", "F24 - Mark overflow offered", ("OverflowOffered", "BOOLEAN", "true"))
f.menu("F24_OverflowMenu", "P22", P["P22"], "F24 - Overflow offer: 1 callback, 2 SMS chat link, 3 keep waiting",
       {"1": "Callback", "2": "Chat link SMS", "3": "Keep waiting"}, timeout=6)
f.callback("F25_Callback", "{{CallerANI}}", "{{CurrentQueueId}}", "F25 - Callback to CallerANI via current queue")
play("F25b_CallbackMsg", "P23", "F25 - Callback confirmation (P23)")
f.disconnect("F25_Disconnect", "F25 - Disconnect after callback registered")
f.http("F26_SendChatLink", "/mpsa-chat-link",
       "F26 - Webex Connect webhook: send SMS chat link to CallerANI. " + CONNECT_CONNECTOR_HINT,
       body='{ "msisdn": "{{CallerANI}}", "template": "chat_link_en" }')
play("F26b_ChatLinkMsg", "P24", "F26 - Chat link sent (P24)")
play("F26e_SmsFailedMsg", "P25", "F26 - SMS failed, stay on the line (P25)")
f.disconnect("F26_Disconnect", "F26 - Disconnect after chat link sent")

# every unverified path enters the general queue through F20a (sets CurrentQueueId)
f.retarget("F20_QueueGeneral", "F20a_SetGeneralQueue")
f.edge("F19a_SetCaseQueue", "F19_QueueCase", "out", "error")
f.edge("F20a_SetGeneralQueue", "F20_QueueGeneral", "out", "error")
f.edge("F19_QueueCase", "F21_WhichQueue", "default")
f.edge("F20_QueueGeneral", "F21_WhichQueue", "default")
f.edge("F21_WhichQueue", "F21c_GetQueueInfo", "true")
f.edge("F21_WhichQueue", "F21g_GetQueueInfo", "false", "error")
for sfx in ("c", "g"):
    f.edge(f"F21{sfx}_GetQueueInfo", f"F21{sfx}b_StoreQueueInfo", "")
    f.edge(f"F21{sfx}_GetQueueInfo", "F23a_IncLoop", "insufficientdata", "failure")
    f.edge(f"F21{sfx}b_StoreQueueInfo", "F22_CheckOverflow", "out")
    f.edge(f"F21{sfx}b_StoreQueueInfo", "F23a_IncLoop", "error")
f.edge("F22_CheckOverflow", "F24a_SetOffered", "true")
f.edge("F22_CheckOverflow", "F23a_IncLoop", "false", "error")
f.edge("F23a_IncLoop", "F23_WaitMsg", "out", "error")
f.edge("F23_WaitMsg", "F23b_Every3rd", "default")
f.edge("F23_WaitMsg", "F23d_HoldMusic", "error")
f.edge("F23b_Every3rd", "F23c_PatienceMsg", "true")
f.edge("F23b_Every3rd", "F23d_HoldMusic", "false", "error")
f.edge("F23c_PatienceMsg", "F23d_HoldMusic", "default", "error")
f.edge("F23d_HoldMusic", "F21_WhichQueue", "default", "error")
f.edge("F24a_SetOffered", "F24_OverflowMenu", "out", "error")
f.edge("F24_OverflowMenu", "F25_Callback", "1")
f.edge("F24_OverflowMenu", "F26_SendChatLink", "2")
f.edge("F24_OverflowMenu", "F23a_IncLoop", "3", "timeout", "invalid", "error")
f.edge("F25_Callback", "F25b_CallbackMsg", "default")
f.edge("F25_Callback", "F23a_IncLoop", "failure")
f.edge("F25b_CallbackMsg", "F25_Disconnect", "default", "error")
f.edge("F26_SendChatLink", "F26b_ChatLinkMsg", "default")
f.edge("F26_SendChatLink", "F26e_SmsFailedMsg", "error")
f.edge("F26b_ChatLinkMsg", "F26_Disconnect", "default", "error")
f.edge("F26e_SmsFailedMsg", "F23a_IncLoop", "default", "error")

# ---------------- 4.5 Event flows ----------------
f.event_flow()
f.event("GlobalErrorHandling", "OnGlobalError - play P30, queue to general enquiries, else disconnect")
play("EV_ErrorMsg", "P30", "OnGlobalError - technical issue (P30)")
f.queue("EV_QueueGeneral", Q_GENERAL, "Q_MPSA_General_Enquiries (placeholder: Queue-1)",
        "OnGlobalError - queue to Q_MPSA_General_Enquiries")
f.disconnect("EV_Disconnect", "OnGlobalError - disconnect if queueing fails")
f.edge("GlobalErrorHandling", "EV_ErrorMsg", "out")
f.edge("EV_ErrorMsg", "EV_QueueGeneral", "default", "error")
f.edge("EV_QueueGeneral", "EV_Disconnect", "default")
f.main_flow()

flow = f
