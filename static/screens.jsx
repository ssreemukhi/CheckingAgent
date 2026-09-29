// Screens for Checking Agent

const { useState, useEffect, useRef, useMemo } = React;

/* ---------------- SHARED HELPERS ---------------- */
function fmtDur(s){
  if (s == null || isNaN(s)) return '—';
  if (s < 60) return s.toFixed(1) + ' s';
  return Math.floor(s/60) + 'm ' + Math.round(s%60) + 's';
}
function fmtTok(n){
  return n == null ? '—' : Number(n).toLocaleString();
}
function mean(arr){
  return arr.length ? arr.reduce((a,b)=>a+b,0)/arr.length : null;
}
function plural(n, word){
  return n + ' ' + word + (n===1 ? '' : 's');
}
function fmtElapsed(s){
  s = Math.max(0, Math.floor(s));
  return s < 60 ? s + ' s' : Math.floor(s/60) + 'm ' + (s%60) + 's';
}
// CSV export of a run (opens in Excel). Cells that start with = + - @ are prefixed with a quote
// so a value read from a PDF can never run as a spreadsheet formula.
function csvCell(v){
  let s = v == null ? '' : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s;
  return '"' + s.replace(/"/g, '""') + '"';
}
function buildCsv(results, remarks){
  const head = ['Section','Field','Left document value','Left page','Right document value','Right page','Result','Conflict inside a document','Note','Analyst remark'];
  const label = r => r.absent ? 'Not in either' : r.status==='match' ? 'Match' : r.status==='mismatch' ? 'Mismatch' : 'Missing';
  const rows = results.map(r => [r.sec, r.field, r.binder, r.pageA, r.policy, r.pageB, label(r), r.conflict, r.note, (remarks || {})[`${r.sec}-${r.field}`]]);
  return '\uFEFF' + [head, ...rows].map(row => row.map(csvCell).join(',')).join('\r\n');
}
// Distinct lines of business among the selected checklists ('any' checklists do not count).
function selectedLines(checklists, selected){
  return [...new Set(checklists.filter(t=>selected.has(t.id) && t.line && t.line!=='any').map(t=>t.lineLabel))];
}

/* ---------------- DASHBOARD ---------------- */
function DashboardScreen({ runs, onNewRun, onOpenRun, onGoto, firestoreStatus }){
  const totalRuns = runs.length;
  const totalMismatches = runs.reduce((a,r)=>a+r.mismatched+r.missing,0);
  const cleanRuns = runs.filter(r=>r.mismatched===0 && r.missing===0).length;

  // Measured usage (only runs that carry a usage block) — used for the processing-time
  // figure below. Token and cost totals live on the Admin console (team-wide, not per-user).
  const measured = runs.filter(r=>r.usage);
  const avgLatency = mean(measured.map(r=>r.usage.latency_s));

  // Display-only figures derived from the runs already loaded.
  const fieldsChecked = runs.reduce((a,r)=>a+(r.fieldCount||0),0);
  const byStatus = {new:0, in_review:0, rejected:0, approved:0};
  runs.forEach(r=>{ const k = r.reviewStatus || 'new'; if (byStatus[k] != null) byStatus[k]++; });
  const awaiting = byStatus.new + byStatus.in_review + byStatus.rejected;
  const saved = firestoreStatus === 'connected';
  const cleanPct = totalRuns ? Math.round(cleanRuns*100/totalRuns) : 0;
  const today = new Date().toLocaleDateString(undefined, {day:'numeric', month:'long', year:'numeric'});
  const headline = totalRuns
    ? `${totalMismatches} ${totalMismatches===1?'Discrepancy':'Discrepancies'} Found Across ${totalRuns} ${totalRuns===1?'Comparison':'Comparisons'}`
    : 'No Comparisons Run Yet';
  const stages = [
    {k:'new',       label:'New',       note:'Not yet reviewed',      tone:'neutral'},
    {k:'in_review', label:'In Review', note:'Remarks in progress',   tone:'info'},
    {k:'rejected',  label:'Rejected',  note:'Sent back for rework',  tone:'bad'},
    {k:'approved',  label:'Approved',  note:'Signed off and locked', tone:'ok'},
  ];

  return (
    <>
      <div className="ca-pagehead">
        <div className="ca-kicker">Dashboard</div>
        <h2>{headline}</h2>
        <p className="ca-lede">
          Each comparison checks every checklist field in both documents, shows the page each value came from, and holds anything flagged until a reviewer signs it off.
        </p>
        <div className="ca-tags">
          <Chip kind="neutral">{today}</Chip>
          {saved
            ? <Chip kind="ok">Run history saved permanently</Chip>
            : <Chip kind="neutral">Run history resets on redeploy</Chip>}
        </div>
      </div>

      <div className="ca-body">
        <div className="ca-dash-hero">
          <section className="ca-panel ca-pipeline">
            <div className="ca-panel-head">
              <h4>Review Pipeline</h4>
              <span className="ca-pipeline-note">{awaiting} {awaiting===1?'run':'runs'} awaiting sign-off</span>
            </div>
            <div className="ca-panel-body">
              <div className="ca-pipeline-bar" role="img" aria-label={stages.map(st=>`${st.label}: ${byStatus[st.k]}`).join(', ')}>
                {stages.map(st => byStatus[st.k] > 0 && <span key={st.k} className={`ca-pipeline-seg ca-seg--${st.tone}`} style={{flexGrow:byStatus[st.k]}}/>)}
              </div>
              <div className="ca-pipeline-stages">
                {stages.map(st=>(
                  <div key={st.k} className="ca-stage">
                    <div className="ca-stage-head"><span className={`ca-stage-dot ca-seg--${st.tone}`}/>{st.label}</div>
                    <div className="ca-stage-value">{byStatus[st.k]}</div>
                    <div className="ca-stage-note">{st.note}</div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="ca-cta" onClick={onNewRun} title="Open New Comparison">
            <h3>Start a New Comparison</h3>
            <ol className="ca-flow">
              <li><span className="ca-flow-num">1</span><div><strong>Upload Two PDFs</strong><span>Binder, policy, quote or endorsement</span></div></li>
              <li><span className="ca-flow-num">2</span><div><strong>Check Every Field</strong><span>Each value shown with the page it came from</span></div></li>
              <li><span className="ca-flow-num">3</span><div><strong>Review and Approve</strong><span>Flagged fields resolved before sign-off</span></div></li>
            </ol>
            <button className="ca-btn is-accent" onClick={onNewRun}><Icon name="newdoc" size={18}/>New Comparison</button>
          </section>
        </div>

        <div className="ca-grid-5" style={{marginBottom:14}}>
          <StatCard label="Comparisons Run" value={totalRuns} sub={saved ? 'All saved runs' : 'Since the last restart'}/>
          <StatCard label="Fields Checked" value={fieldsChecked.toLocaleString()} sub="Across all comparisons"/>
          <StatCard label="Discrepancies Flagged" value={totalMismatches} sub="Mismatched or missing fields" tone="wrn"/>
          <StatCard label="Clean Comparisons" value={cleanRuns} sub={totalRuns ? `${cleanPct}% with no discrepancies` : 'No runs yet'} tone="suc"/>
          <StatCard label="Avg. Processing Time" value={fmtDur(avgLatency)} sub={measured.length ? `Measured over ${plural(measured.length,'run')}` : 'No measured runs yet'}/>
        </div>

        <SectionHead title="Recent Runs" sub="Latest 5 comparisons" right={<a href="#" onClick={e=>{e.preventDefault();onGoto('history')}}>View all runs</a>}/>
        <div className="ca-panel is-wide">
          <table className="ca-table">
            <thead><tr>
              <th>Account</th><th>Date / Owner</th><th>Status</th><th className="ca-center">Matched</th><th className="ca-center">Mismatched</th><th className="ca-center">Missing</th><th className="ca-center">Tokens</th><th></th>
            </tr></thead>
            <tbody>
              {runs.slice(0,5).map(r=>(
                <tr key={r.id} className={r.mismatched===0 && r.missing===0 ? 'is-clean' : ''}>
                  <td>
                    <div className="ca-run-title">{r.account}</div>
                    <div className="ca-run-sub">{r.binder} ↔ {r.policy}</div>
                  </td>
                  <td>
                    <div>{r.date}</div>
                    <div className="ca-run-sub">{r.user}</div>
                  </td>
                  <td><StatusBadge status={r.reviewStatus}/></td>
                  <td className="ca-center"><span className="ca-badge ca-badge--ok">{r.matched}</span></td>
                  <td className="ca-center">{r.mismatched>0 ? <span className="ca-badge ca-badge--bad">{r.mismatched}</span> : <span style={{color:'var(--ca-muted)'}}>—</span>}</td>
                  <td className="ca-center">{r.missing>0 ? <span className="ca-badge ca-badge--warn">{r.missing}</span> : <span style={{color:'var(--ca-muted)'}}>—</span>}</td>
                  <td className="ca-center">{r.usage ? fmtTok(r.usage.total_tokens) : '—'}</td>
                  <td style={{textAlign:'right'}}><button className="ca-btn is-quiet is-small" onClick={()=>onOpenRun(r)}>Open</button></td>
                </tr>
              ))}
              {runs.length === 0 && (
                <tr><td colSpan={8} style={{padding:'28px',textAlign:'center',color:'var(--ca-muted)',fontStyle:'italic'}}>No runs yet. Start a new comparison to see results here.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

/* ---------------- ID NUMBER FORMAT CHECK (mirrors id_validation.py) ---------------- */
const VH_D=[[0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],[4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],[8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0]];
const VH_P=[[0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],[9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8]];
function verhoeffOk(num){
  let c=0; const d=num.split('').reverse();
  for(let i=0;i<d.length;i++) c=VH_D[c][VH_P[i%8][+d[i]]];
  return c===0;
}
// Returns an error string, or null if the number is well-formed (or the type has no rule).
// Format only — never authenticity. The server re-checks with the same rules.
function idNumberError(type, value){
  const n=(value||'').replace(/[\s-]/g,'').toUpperCase();
  if(!n) return null;
  const t=(type||'').trim().toLowerCase();
  if(t==='aadhaar'){
    if(!/^\d+$/.test(n)) return 'Aadhaar must contain digits only.';
    if(n.length!==12) return `Aadhaar must be exactly 12 digits (got ${n.length}).`;
    if(/^[01]/.test(n)) return 'Aadhaar cannot start with 0 or 1.';
    if(!verhoeffOk(n)) return 'Aadhaar check digit is invalid — likely a typo.';
    return null;
  }
  if(t==='pan'){
    if(n.length!==10) return `PAN must be exactly 10 characters (got ${n.length}).`;
    if(!/^[A-Z]{5}\d{4}[A-Z]$/.test(n)) return 'PAN must be 5 letters, 4 digits, 1 letter (e.g. ABCPE1234F).';
    if(!'ABCFGHJLPT'.includes(n[3])) return 'PAN 4th character is not a valid holder type.';
    return null;
  }
  if(t==='passport') return /^[A-Z]\d{7}$/.test(n) ? null : 'Indian passport number must be 1 letter followed by 7 digits (e.g. K1234567).';
  if(t==='voter id') return /^[A-Z]{3}\d{7}$/.test(n) ? null : 'Voter ID (EPIC) must be 3 letters followed by 7 digits.';
  return null;
}
const ID_PLACEHOLDER={Aadhaar:'e.g. 2345 6789 0124',PAN:'e.g. ABCPE1234F',Passport:'e.g. K1234567','Voter ID':'e.g. ABC1234567'};

/* ---------------- NEW RUN — UPLOAD + CHECKLISTS ---------------- */
function NewRunScreen({ onProcess, onCancel, checklists=[], checklistsError=null, recentAccounts=[], me }){
  const [docLeft, setDocLeft] = useState(null);
  const [docRight, setDocRight] = useState(null);
  const [typeLeft, setTypeLeft] = useState('Binder');
  const [typeRight, setTypeRight] = useState('Policy');
  const [account, setAccount] = useState('');
  const [policyEffective, setPolicyEffective] = useState('');
  const [runOwner, setRunOwner] = useState('');
  const [showIdCheck, setShowIdCheck] = useState(false);
  const [idName, setIdName] = useState('');
  const [idType, setIdType] = useState('Aadhaar');
  const [idTypeOther, setIdTypeOther] = useState('');
  const [idNumber, setIdNumber] = useState('');
  // What actually goes to the server — plain fields in, the same JSON shape out, so
  // main.py needs no changes at all for this to work.
  const idDataJson = idName.trim() ? JSON.stringify({
    fullName: idName.trim(),
    idType: (idType === 'Other' ? idTypeOther : idType).trim() || undefined,
    idNumber: idNumber.trim() || undefined,
  }) : '';
  const ownerPrefilled = useRef(false); // only ever auto-fill once, and only if the person hasn't typed anything

  // Pre-fill from the verified identity once it's known, so 'Run Owner' isn't left blank
  // by default. It stays a normal editable text box — nothing stops someone typing over it.
  useEffect(()=>{
    if (!ownerPrefilled.current && me && me.email && !runOwner) {
      setRunOwner(me.email);
      ownerPrefilled.current = true;
    }
  }, [me]);
  const [selected, setSelected] = useState(new Set());

  const DOC_TYPES = ['Binder','Quote','Policy','Endorsement','Renewal'];

  function toggleCl(id){
    setSelected(s=>{ const n=new Set(s); if(n.has(id))n.delete(id);else n.add(id); return n; });
  }

  function pickFile(setter){
    return () => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.pdf';
      input.onchange = (e) => {
        const f = e.target.files[0];
        if (!f) return;
        setter({name: f.name, size: (f.size/1024/1024).toFixed(1)+' MB', file: f});
      };
      input.click();
    };
  }

  // Number of distinct fields the selected checklists will check (a field
  // shared by two checklists is only checked once).
  const fieldsTotal = useMemo(()=>{
    const seen = new Set();
    checklists.filter(t=>selected.has(t.id)).forEach(t=>t.fields.forEach(f=>seen.add(f.section+'|'+f.field)));
    return seen.size;
  },[checklists, selected]);

  const idErr = showIdCheck ? idNumberError(idType === 'Other' ? idTypeOther : idType, idNumber) : null;
  const ready = docLeft && docRight && selected.size>0 && !idErr;
  const lineLabels = selectedLines(checklists, selected);

  return (
    <>
      <div className="ca-pagehead">
        <div className="ca-kicker">New Comparison</div>
        <h2>New Policy Comparison</h2>
        <p className="ca-lede">Upload both documents, identify each type, and select the checklists to apply. Each run checks exactly the fields in the checklists you select, so choose the ones that fit the document type.</p>
        <div className="ca-tags">
          <Chip kind="neutral">Step 1 of 3 — Upload & Configure</Chip>
          {ready && <Chip kind="ok">Ready to run — {plural(fieldsTotal,'field')} will be checked</Chip>}
        </div>
      </div>

      <div className="ca-body">
        {/* Account / metadata */}
        <SectionHead title="Account Details" sub="Metadata for audit log"/>
        <div className="ca-panel is-wide">
          <div className="ca-panel-body" style={{display:'grid',gridTemplateColumns:'2fr 1fr 1fr',gap:14}}>
            <div className="ca-field">
              <label className="ca-label">Account / Insured</label>
              <input className="ca-input" list="recent-accounts" value={account} onChange={e=>setAccount(e.target.value)} placeholder="Search or enter account"/>
              <datalist id="recent-accounts">
                {recentAccounts.map(a => <option key={a} value={a}/>)}
              </datalist>
            </div>
            <div className="ca-field">
              <label className="ca-label">Policy Effective</label>
              <input className="ca-input" type="date" value={policyEffective} onChange={e=>setPolicyEffective(e.target.value)}/>
            </div>
            <div className="ca-field">
              <label className="ca-label">Run Owner</label>
              <input className="ca-input" type="text" value={runOwner} onChange={e=>setRunOwner(e.target.value)} placeholder="Your name"/>
            </div>
          </div>
        </div>

        {/* Upload area */}
        <SectionHead title="Documents" sub="PDF only · up to 25 MB each"/>
        <div className="ca-grid-2 ca-keep is-wide" style={{marginBottom:14}}>
          {[
            {doc:docLeft, set:setDocLeft, type:typeLeft, setType:setTypeLeft, side:'Left / Source'},
            {doc:docRight, set:setDocRight, type:typeRight, setType:setTypeRight, side:'Right / Target'},
          ].map((c,i)=>(
            <div key={i}>
              <div className={`ca-dropzone ${c.doc?'filled':''}`} onClick={pickFile(c.set)}>
                <div className="ca-dropzone-icon"><Icon name={c.doc ? 'check' : 'upload'} size={26}/></div>
                <div className="ca-dropzone-title">{c.doc ? c.doc.name : c.side}</div>
                <div className="ca-muted">
                  {c.doc ? `${c.doc.size} — click to replace` : 'Click to browse for a PDF'}
                </div>
                <div className="ca-doctypes" onClick={e=>e.stopPropagation()}>
                  {DOC_TYPES.map(t=>(
                    <button key={t} className={`ca-doctype ${c.type===t?'active':''}`} onClick={()=>c.setType(t)}>{t}</button>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Checklists */}
        <SectionHead title="Applicable Checklists" sub="Select at least one · each run checks the fields of the checklists selected" right={<span>{selected.size} selected · {plural(fieldsTotal,'field')}</span>}/>
        <div className="ca-panel is-wide">
          <div className="ca-panel-body">
            {checklistsError && (
              <div style={{padding:'12px 0',color:'var(--ca-bad)',fontSize:'.8125rem'}}>{checklistsError}</div>
            )}
            {!checklistsError && checklists.length===0 && (
              <div style={{padding:'12px 0',color:'var(--ca-muted)',fontStyle:'italic',fontSize:'.8125rem'}}>Loading checklists…</div>
            )}
            {checklists.map(t=>(
              <div key={t.id} className={`ca-check-row ${selected.has(t.id)?'selected':''}`} onClick={()=>toggleCl(t.id)}>
                <div className="ca-checkbox">{selected.has(t.id) ? <Icon name="check" size={13}/> : ''}</div>
                <div style={{flex:1,minWidth:0}}>
                  <div className="ca-check-name">{t.name} <span style={{fontWeight:'normal',color:'var(--ca-muted)',fontSize:'.6875rem',marginLeft:6}}>· {t.type}</span></div>
                  <div className="ca-check-meta">{t.desc}</div>
                  <div className="ca-check-meta" style={{marginTop:2}}>Applies to: {t.lineLabel || 'Any policy'}</div>
                  <div className="ca-check-meta" style={{marginTop:2}}>Fields: {t.fields.map(f=>f.field).join(', ')}</div>
                </div>
                <span className="ca-check-count">{plural(t.fieldCount,'field')}</span>
              </div>
            ))}
          </div>
        </div>

        {lineLabels.length > 1 && (
          <Verdict kind="wrn" icon="!" title="Checklists for different lines of business are selected">
            You selected checklists for {lineLabels.join(' and ').toLowerCase()}. Fields that do not apply to your documents will be reported as not found in either document.
          </Verdict>
        )}

        <SectionHead title="Identity Check (Optional)" sub="Compares the Named Insured field against a supporting ID — a third, independent reference, not an authority"/>
        <div className="ca-panel is-wide">
          <div className="ca-panel-body">
            {!showIdCheck ? (
              <button className="ca-btn is-quiet is-small" onClick={()=>setShowIdCheck(true)}>+ Add ID data to check against</button>
            ) : (
              <div style={{display:'grid',gridTemplateColumns:idType==='Other'?'2fr 1fr 1fr 1fr':'2fr 1fr 1fr',gap:12}}>
                <div className="ca-field">
                  <label className="ca-label">Full name on ID</label>
                  <input className="ca-input" value={idName} onChange={e=>setIdName(e.target.value)} placeholder="e.g. Smith R. Wilson"/>
                </div>
                <div className="ca-field">
                  <label className="ca-label">ID type</label>
                  <select className="ca-input" value={idType} onChange={e=>setIdType(e.target.value)}>
                    <option>Aadhaar</option>
                    <option>PAN</option>
                    <option>Passport</option>
                    <option>Driving Licence</option>
                    <option>Voter ID</option>
                    <option>Other</option>
                  </select>
                </div>
                {idType==='Other' && (
                  <div className="ca-field">
                    <label className="ca-label">Which type?</label>
                    <input className="ca-input" value={idTypeOther} onChange={e=>setIdTypeOther(e.target.value)} placeholder="e.g. National ID"/>
                  </div>
                )}
                <div className="ca-field">
                  <label className="ca-label">ID number <span style={{fontWeight:'normal',color:'var(--ca-muted)'}}>(optional)</span></label>
                  <input className="ca-input" value={idNumber} onChange={e=>setIdNumber(e.target.value)} placeholder={ID_PLACEHOLDER[idType] || 'ID number'} style={idErr ? {borderColor:'var(--ca-bad)'} : undefined}/>
                  {idErr && <div style={{fontSize:'.75rem',color:'var(--ca-bad)',marginTop:4}}>{idErr}</div>}
                </div>
              </div>
            )}
            {showIdCheck && (
              <button className="ca-btn is-quiet is-small" style={{marginTop:10}} onClick={()=>{setShowIdCheck(false); setIdName(''); setIdNumber(''); setIdTypeOther('');}}>Remove</button>
            )}
          </div>
        </div>

        <div style={{display:'flex',gap:8,justifyContent:'flex-end',marginTop:6}}>
          <button className="ca-btn is-quiet" onClick={onCancel}>Cancel</button>
          <button className="ca-btn is-primary" disabled={!ready} onClick={()=>onProcess({account,policyEffective,runOwner,docLeft,docRight,typeLeft,typeRight,selected:[...selected],idData:showIdCheck?idDataJson:''})}>
            Run Comparison →
          </button>
        </div>
      </div>
    </>
  );
}

/* ---------------- PROCESSING ---------------- */
function ProcessingScreen({ onDone, account, typeLeft, typeRight, resultPromise, typicalSeconds }){
  const steps = [
    {key:'parse',label:'Parsing documents · extracting text'},
    {key:'extract',label:'LLM extraction · identifying fields and values'},
    {key:'resolve',label:'Resolving fields to check'},
    {key:'compare',label:'Running field-by-field comparison'},
    {key:'score',label:'Scoring results and generating summary'},
  ];
  const [progress, setProgress] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState(null);

  useEffect(()=>{
    if (!resultPromise) {
      setError('No comparison in progress. This can happen after a page refresh — please start a new comparison.');
      return;
    }

    // The elapsed time is real. The bar is an estimate paced to the typical run
    // time (or 30 s when there is no history yet): it keeps creeping toward 92%
    // and reaches 100% only when the backend has actually answered.
    const start = Date.now();
    const expected = typicalSeconds && typicalSeconds > 5 ? typicalSeconds : 30;
    const id = setInterval(()=>{
      const sec = (Date.now() - start) / 1000;
      setElapsed(sec);
      setProgress(92 * (1 - Math.exp(-sec / (expected * 0.6))));
    }, 200);

    resultPromise
      .then(realResult => {
        clearInterval(id);
        setProgress(100);
        setTimeout(()=>onDone(realResult), 400);
      })
      .catch(err => {
        clearInterval(id);
        setError(err.message || 'Comparison failed.');
      });

    return () => clearInterval(id);
  },[]);

  const curStep = Math.min(steps.length-1, Math.floor(progress/(100/steps.length)));

  if (error) {
    return (
      <div className="ca-body">
        <Verdict kind="dng" icon="✕" title="Comparison failed">{error}</Verdict>
      </div>
    );
  }

  return (
    <>
      <div className="ca-pagehead">
        <div className="ca-kicker">Processing</div>
        <h2>Running Comparison{account ? ` — ${account}` : ''}</h2>
        <p className="ca-lede">Checking Agent is reading both documents and extracting field values with the comparison model. Time depends on document length.</p>
        <div className="ca-tags">
          <Chip kind="neutral">Step 2 of 3 — Processing</Chip>
          <Chip kind="ok">Do not close this tab</Chip>
        </div>
      </div>
      <div className="ca-body">
        <div className="ca-progress">
          <h3>Comparing {typeLeft||'Document A'} Against {typeRight||'Document B'}</h3>
          <div className="ca-muted">Elapsed {fmtElapsed(elapsed)}{typicalSeconds ? ` · typically about ${Math.round(typicalSeconds)} s on this deployment` : ''}</div>
          {elapsed > 90 && <div className="ca-muted">Taking longer than usual. Long policies can take a minute or more, and the run stops with an error after 5 minutes.</div>}
          <div className="ca-progress-track"><div className="ca-progress-fill" style={{width:`${progress}%`}}/></div>
          <div className="ca-steps">
            {steps.map((s,i)=>(
              <div key={s.key} className={`ca-step ${i<curStep?'done':i===curStep?'active':''}`}>
                <div className="ca-step-marker">{i<curStep?<Icon name="check" size={13}/>:(i+1)}</div>
                <div className="ca-step-label">{s.label}</div>
                <div className="ca-step-time">{i<curStep ? 'Complete' : i===curStep ? 'Running…' : 'Queued'}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}

/* ---------------- RESULTS ---------------- */
// A field needs review before approval — same rule the server checks, kept in sync
// on purpose. Mirrors main.py's _discrepancy_keys: mismatches, plus 'missing' fields
// genuinely present on only one side (not the 'absent from both' bucket).
// Same 4 stages everywhere a run's review status is shown — one source of truth for
// the label and color, so Dashboard/History/Admin/Results can never disagree.
const STATUS_LABELS = {new: 'New', in_review: 'In Review', rejected: 'Rejected', approved: 'Approved'};
const STATUS_CLASSES = {new: 'ca-badge--neutral', in_review: 'ca-badge--info', rejected: 'ca-badge--bad', approved: 'ca-badge--ok'};
function StatusBadge({ status }){
  const s = status || 'new';
  return <span className={`ca-badge ${STATUS_CLASSES[s] || 'ca-badge--neutral'}`}>{STATUS_LABELS[s] || s}</span>;
}

// The full audit trail for one run: created, every remarks save (with what it actually
// said), every rejection ever issued (not just the current one), and approval — merged
// into one chronological list. Sorted by each event's own ISO timestamp (the created
// event has none and is never sorted with generated fields; it is unconditionally first,
// since nothing can happen to a run before it exists).
function buildWorkflowEvents(meta){
  const events = [];
  events.push({type:'created', by: meta.runOwner || meta.ownerEmail || 'Unknown', when: meta.date, sortKey: ''});
  (meta.remarkVersions || []).forEach(v => events.push({
    type:'remarks', version: v.version, by: v.savedBy, when: v.savedAt, remarks: v.remarks, sortKey: v.savedAtIso || ''
  }));
  (meta.rejectionHistory || []).forEach(r => events.push({
    type:'rejected', by: r.rejectedBy, when: r.rejectedAt, reason: r.reason, sortKey: r.rejectedAtIso || ''
  }));
  if (meta.approval) events.push({
    type:'approved', by: meta.approval.approvedBy, when: meta.approval.approvedAt, sortKey: meta.approval.approvedAtIso || ''
  });
  const [first, ...rest] = events;
  rest.sort((a,b) => a.sortKey.localeCompare(b.sortKey));
  return [first, ...rest];
}

const EVENT_LABEL = {created:'Run created', remarks:'Remarks saved', rejected:'Rejected', approved:'Approved'};
const EVENT_CLASS  = {created:'ca-badge--neutral', remarks:'ca-badge--info', rejected:'ca-badge--bad', approved:'ca-badge--ok'};

function WorkflowHistoryTimeline({ meta }){
  const events = buildWorkflowEvents(meta);
  return (
    <div>
      {events.map((e,i)=>(
        <div key={i} style={{display:'flex',gap:12,marginBottom:14}}>
          <div style={{flexShrink:0,width:14,display:'flex',flexDirection:'column',alignItems:'center'}}>
            <div style={{width:10,height:10,borderRadius:'50%',background:'var(--ca-ink,#1D2B33)',marginTop:4}}/>
            {i < events.length-1 && <div style={{flex:1,width:2,background:'var(--ca-line,#D6DCDB)',marginTop:2}}/>}
          </div>
          <div style={{flex:1,paddingBottom:4}}>
            <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:2}}>
              <span className={`ca-badge ${EVENT_CLASS[e.type]}`}>{EVENT_LABEL[e.type]}{e.type==='remarks' ? ` — V${e.version}` : ''}</span>
              <span style={{fontSize:'.75rem',color:'var(--ca-muted)'}}>{e.by} · {e.when || 'Not recorded'}</span>
            </div>
            {e.type === 'rejected' && (
              <div style={{fontSize:'.8125rem',color:'var(--ca-ink)',background:'#F8E1DE',borderRadius:4,padding:'6px 10px',marginTop:4}}>
                {e.reason || 'No reason given.'}
              </div>
            )}
            {e.type === 'remarks' && (()=>{
              const entries = Object.entries(e.remarks || {}).filter(([,v]) => (v.text && v.text.trim()) || v.resolved);
              if (entries.length === 0) return <div style={{fontSize:'.75rem',color:'var(--ca-muted)',fontStyle:'italic'}}>No notes or resolved fields in this version.</div>;
              return (
                <table className="ca-table" style={{marginTop:4,border:'1px solid var(--ca-line)'}}>
                  <tbody>
                    {entries.map(([key, v])=>(
                      <tr key={key}>
                        <td style={{fontSize:'.75rem',color:'var(--ca-ink)',fontWeight:'bold',width:'35%'}}>{key.split('-').slice(1).join('-')}</td>
                        <td style={{fontSize:'.75rem'}}>{v.text || <em style={{color:'var(--ca-muted)'}}>(no note)</em>}</td>
                        <td style={{fontSize:'.75rem',width:90,textAlign:'right'}}>{v.resolved ? <span className="ca-badge ca-badge--ok">Resolved</span> : <span style={{color:'var(--ca-muted)'}}>Open</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              );
            })()}
          </div>
        </div>
      ))}
    </div>
  );
}

function needsResolution(r){
  return r.status === 'mismatch' || (r.status === 'missing' && !r.absent);
}

// Renders a computed line diff (see main.py's compute_doc_diff) as a two-column view:
// removed/changed lines highlighted red on the left, added/changed lines highlighted
// green on the right, long unchanged runs collapsed to a single grey summary row.
function DocDiffView({ diff, typeLeft, typeRight, pagesLeft, pagesRight }){
  if (!diff) {
    const known = pagesLeft != null && pagesRight != null;
    return (
      <div style={{padding:'20px',color:'var(--ca-muted)',fontSize:'.8125rem',fontStyle:'italic',textAlign:'center'}}>
        No line-by-line comparison shown — this is expected, not an error.{' '}
        {known
          ? `${typeLeft} is ${pagesLeft} page${pagesLeft===1?'':'s'} and ${typeRight} is ${pagesRight} page${pagesRight===1?'':'s'} — too different in length for a line-by-line view to be useful (nearly everything would show as "different"). `
          : 'These documents are too different in length, or too long, for a useful line-by-line view. '}
        See the Results tab for the field-level comparison instead. Try this on two versions of the same document (e.g. a binder and its correction) to see the diff working.
      </div>
    );
  }
  const rowStyle = {display:'grid',gridTemplateColumns:'1fr 1fr',gap:1,fontFamily:'monospace',fontSize:'.75rem',lineHeight:1.5};
  const cell = (bg) => ({background:bg,padding:'2px 10px',whiteSpace:'pre-wrap',wordBreak:'break-word'});
  return (
    <div style={{border:'1px solid var(--ca-line)',borderRadius:4,overflow:'hidden'}}>
      <div style={rowStyle}>
        <div style={{...cell('var(--ca-row)'),fontWeight:'bold',fontFamily:'inherit'}}>{typeLeft}</div>
        <div style={{...cell('var(--ca-row)'),fontWeight:'bold',fontFamily:'inherit'}}>{typeRight}</div>
      </div>
      {diff.map((c,i)=>{
        if (c.type === 'equal_collapsed') {
          return <div key={i} style={{...rowStyle,gridTemplateColumns:'1fr'}}><div style={{...cell('#fff'),color:'var(--ca-muted)',fontStyle:'italic',fontFamily:'inherit',textAlign:'center'}}>— {c.count} unchanged line{c.count===1?'':'s'} —</div></div>;
        }
        const left = c.left || [], right = c.right || [];
        const rows = Math.max(left.length, right.length, 1);
        return Array.from({length: rows}).map((_,r)=>(
          <div key={i+'-'+r} style={rowStyle}>
            <div style={cell(c.type==='left_only'||c.type==='replace' ? '#F8E1DE' : '#fff')}>{left[r] ?? ''}</div>
            <div style={cell(c.type==='right_only'||c.type==='replace' ? '#DDF1E7' : '#fff')}>{right[r] ?? ''}</div>
          </div>
        ));
      })}
    </div>
  );
}

function ResultsScreen({ results, meta, me, onNew, onGoto, onRunUpdated }){
  const [filter, setFilter] = useState('all');
  // Shape: { 'section-field': {text, resolved} }. Initialized from the latest saved
  // version if this run has one — so reopening a run you already annotated doesn't
  // start blank — otherwise empty, same as a brand-new run.
  const [remarks, setRemarks] = useState(()=>{
    const versions = meta.remarkVersions || [];
    return versions.length ? {...versions[versions.length-1].remarks} : {};
  });
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState(null);
  const [rejecting, setRejecting] = useState(false);
  const [rejectError, setRejectError] = useState(null);
  const [showRejectBox, setShowRejectBox] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [tab, setTab] = useState('results');
  const [sectionFilter, setSectionFilter] = useState('all');
  const approved = !!meta.approval;
  const versions = meta.remarkVersions || [];

  const counts = useMemo(()=>{
    const c={match:0,mismatch:0,missing:0,absent:0};
    results.forEach(r=>{ if (r.absent) c.absent++; else if (c[r.status] != null) c[r.status]++; });
    return c;
  },[results]);

  const filtered = results.filter(r=>{
    if (filter !== 'all' && (r.absent ? 'absent' : r.status) !== filter) return false;
    if (sectionFilter !== 'all' && r.sec !== sectionFilter) return false;
    return true;
  });

  const sections = [...new Set(results.map(r=>r.sec))];
  const grouped = useMemo(()=>{
    const g = {};
    filtered.forEach(r => { (g[r.sec] = g[r.sec] || []).push(r); });
    return g;
  }, [filtered]);

  const remarkCount = Object.values(remarks).filter(v=>v && v.text && v.text.trim()).length;
  const needing = useMemo(()=>results.filter(needsResolution), [results]);
  const unresolvedCount = needing.filter(r => !(remarks[`${r.sec}-${r.field}`]||{}).resolved).length;

  function setRemarkText(key, text){
    setRemarks(rr => ({...rr, [key]: {...(rr[key]||{resolved:false}), text}}));
  }
  function setRemarkResolved(key, resolved){
    setRemarks(rr => ({...rr, [key]: {...(rr[key]||{text:''}), resolved}}));
  }

  function saveRemarks(){
    if (saving || approved) return;
    setSaving(true); setSaveError(null);
    fetch(`/api/history/${meta.runId}/remarks`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({remarks}),
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not save remarks.');
        return data;
      })
      .then(data => onRunUpdated && onRunUpdated({remarkVersions: data.remarkVersions}))
      .catch(e => setSaveError(e.message))
      .finally(() => setSaving(false));
  }

  function approveRun(){
    if (approving || approved) return;
    setApproving(true); setApproveError(null);
    fetch(`/api/history/${meta.runId}/approve`, {method: 'POST'})
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not approve this run.');
        return data;
      })
      .then(data => onRunUpdated && onRunUpdated({approval: data.approval, reviewStatus: data.reviewStatus}))
      .catch(e => setApproveError(e.message))
      .finally(() => setApproving(false));
  }

  function rejectRun(){
    if (rejecting || approved) return;
    setRejecting(true); setRejectError(null);
    fetch(`/api/history/${meta.runId}/reject`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({reason: rejectReason}),
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not reject this run.');
        return data;
      })
      .then(data => {
        onRunUpdated && onRunUpdated({rejection: data.rejection, rejectionHistory: data.rejectionHistory, reviewStatus: data.reviewStatus});
        setShowRejectBox(false); setRejectReason('');
      })
      .catch(e => setRejectError(e.message))
      .finally(() => setRejecting(false));
  }

  function exportCsv(){
    const flatRemarks = Object.fromEntries(Object.entries(remarks).map(([k,v])=>[k, v && v.text]));
    const blob = new Blob([buildCsv(results, flatRemarks)], {type:'text/csv;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `checking-agent-${meta.runId || 'run'}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    setTimeout(()=>URL.revokeObjectURL(url), 1000);
  }

  // Usage block (absent on runs from before usage tracking)
  const u = meta.usage || null;
  const tok = n => (n == null ? 'Not recorded' : Number(n).toLocaleString());
  const costText = !u ? 'Not recorded'
    : u.est_cost_usd == null ? 'Rate not configured'
    : '$' + u.est_cost_usd.toFixed(4);
  const cut = u && u.truncated
    ? [u.truncated.left && (meta.typeLeft || 'Left document'), u.truncated.right && (meta.typeRight || 'Right document')].filter(Boolean)
    : null;
  const pctMatched = results.length ? Math.round(counts.match/results.length*100) : 0;
  const modelName = (u && u.model) ? u.model : 'Not recorded';
  const applied = meta.checklists || [];
  const appliedText = applied.length ? applied.map(c=>c.name).join(', ') : 'Not recorded';
  const unreturned = u && u.unreturned ? u.unreturned : 0;
  const conflictCount = results.filter(r=>r.conflict).length;
  const discrepancies = counts.mismatch + counts.missing;   // fields found in neither document are not counted
  const discWord = discrepancies === 1 ? 'discrepancy' : 'discrepancies';

  return (
    <>
      <div className="ca-pagehead">
        <div className="ca-kicker">Results</div>
        <h2>{meta.account} — {discrepancies} {discWord.charAt(0).toUpperCase()+discWord.slice(1)} Found</h2>
        <p className="ca-lede">
          Comparison of <strong style={{color:'var(--ca-ink)'}}>{meta.docLeft?.name}</strong> ({meta.typeLeft}) against <strong style={{color:'var(--ca-ink)'}}>{meta.docRight?.name}</strong> ({meta.typeRight}). Review the flagged fields and add your own notes for carrier follow-up.
        </p>
        <div className="ca-tags">
          <Chip kind="ok">{counts.match} matched</Chip>
          <Chip kind="bad">{counts.mismatch} mismatched</Chip>
          <Chip kind="warn">{counts.missing} missing</Chip>
          {counts.absent > 0 && <Chip kind="neutral">{counts.absent} not in either</Chip>}
          <Chip kind="neutral">{results.length} fields · {applied.length ? plural(applied.length,'checklist') : 'checklists not recorded'}</Chip>
          {conflictCount > 0 && <Chip kind="warn">{plural(conflictCount,'conflict')} inside a document</Chip>}
          <Chip kind="neutral">Run {meta.runId || '—'} · Completed {meta.date || 'Not recorded'}</Chip>
        </div>
        <div className="ca-tags" style={{marginTop:6}}><StatusBadge status={meta.reviewStatus}/></div>
      </div>

      <div className="ca-body">
        <div className="ca-grid-4" style={{marginBottom:14}}>
          <StatCard label="Matched" value={counts.match} sub={`${pctMatched}% of ${results.length} fields`} tone="suc"/>
          <StatCard label="Mismatched" value={counts.mismatch} sub="Requires carrier review" tone="dng"/>
          <StatCard label="Missing" value={counts.missing} sub="Present in only one document" tone="wrn"/>
          <StatCard label="Not in Either" value={counts.absent} sub="Nothing to compare · not counted"/>
        </div>

        {discrepancies === 0 ? (
          <Verdict kind="suc" icon="✓" title="All checked fields match">
            No discrepancies detected across {plural(results.length - counts.absent,'comparable field')}.{counts.absent > 0 ? ` ${plural(counts.absent,'field')} found in neither document ${counts.absent===1?'is':'are'} not counted.` : ''}
          </Verdict>
        ) : (
          <Verdict kind="wrn" icon="!" title={`${discrepancies} ${discWord} ${discrepancies===1?'needs':'need'} review`}>
            Review each flagged row and add your assessment. A field marked missing appears in only one of the two documents, which is not always an error.{counts.absent > 0 ? ` ${plural(counts.absent,'field')} found in neither document ${counts.absent===1?'is':'are'} not counted.` : ''} Notes are kept on this screen only and are not saved with the run.
          </Verdict>
        )}

        {conflictCount > 0 && (
          <Verdict kind="wrn" icon="!" title="A document gives different values for the same field">
            {plural(conflictCount,'field')} appear{conflictCount===1?'s':''} with different values in different places inside one document. The value shown is the one from the earliest page, and the note on each row names the other. Check the source PDF before relying on the result.
          </Verdict>
        )}

        {cut && cut.length > 0 && (
          <Verdict kind="wrn" icon="!" title="Document text was cut off before comparison">
            Only the first part of the {cut.join(' and ')} document{cut.length===1?'':'s'} was sent to the model, so fields that appear later may be reported as missing. Confirm any "missing" result against the source PDF.
          </Verdict>
        )}

        {meta.identityCheck && (()=>{
          const ic = meta.identityCheck;
          const label = (m) => m === true ? <span className="ca-badge ca-badge--ok">Matches</span> : m === false ? <span className="ca-badge ca-badge--bad">Does not match</span> : <span style={{color:'var(--ca-muted)'}}>—</span>;
          const bothAgree = results.find(r => r.field === 'Named Insured')?.status === 'match';
          return (
            <div className="ca-panel is-wide" style={{marginBottom:14}}>
              <div className="ca-panel-body">
                <div style={{fontSize:'.75rem',fontWeight:'bold',color:'var(--ca-ink)',letterSpacing:'.03em',textTransform:'uppercase',marginBottom:8}}>
                  Identity Check {ic.idType ? `— ${ic.idType}` : ''}
                </div>
                <table className="ca-table" style={{border:'1px solid var(--ca-line)'}}>
                  <tbody>
                    <tr><td style={{width:'30%',color:'var(--ca-muted)'}}>Name on ID</td><td style={{fontWeight:'bold'}}>{ic.idName}{ic.idNumber ? ` (${ic.idNumber})` : ''}</td></tr>
                    <tr><td style={{color:'var(--ca-muted)'}}>Binder Named Insured</td><td>{ic.binderValue} {label(ic.binderMatches)}</td></tr>
                    <tr><td style={{color:'var(--ca-muted)'}}>Policy Named Insured</td><td>{ic.policyValue} {label(ic.policyMatches)}</td></tr>
                  </tbody>
                </table>
                {ic.idNumberError && (
                  <div style={{fontSize:'.8125rem',color:'var(--ca-bad)',marginTop:8}}>ID number was invalid, so the identity was not checked: {ic.idNumberError}</div>
                )}
                {bothAgree && ic.binderMatches === false && ic.policyMatches === false && (
                  <div style={{fontSize:'.75rem',color:'#9A6200',marginTop:8}}>Binder and Policy agree with each other, but neither matches the ID on file — worth a closer look.</div>
                )}
                {!bothAgree && ic.binderMatches !== ic.policyMatches && (
                  <div style={{fontSize:'.75rem',color:'var(--ca-muted)',marginTop:8}}>Binder and Policy disagree with each other; the ID on file agrees with {ic.policyMatches ? 'the Policy' : 'the Binder'}.</div>
                )}
              </div>
            </div>
          );
        })()}

        {unreturned > 0 && (
          <Verdict kind="wrn" icon="!" title={`${plural(unreturned,'field')} not returned by the model`}>
            The model gave no answer for {unreturned===1?'one field':unreturned+' fields'}. They are shown as missing with a note. Run the comparison again, or check them against the source PDFs.
          </Verdict>
        )}

        {/* Tabs */}
        <div className="ca-panel is-wide" style={{padding:0}}>
          <div className="ca-tabs" style={{padding:'0 16px'}}>
            <button className={`ca-tab ${tab==='results'?'active':''}`} onClick={()=>setTab('results')}>Results</button>
            <button className={`ca-tab ${tab==='summary'?'active':''}`} onClick={()=>setTab('summary')}>Summary by Section</button>
            <button className={`ca-tab ${tab==='docs'?'active':''}`} onClick={()=>setTab('docs')}>Documents</button>
            <button className={`ca-tab ${tab==='log'?'active':''}`} onClick={()=>setTab('log')}>Run Metadata</button>
            <button className={`ca-tab ${tab==='history'?'active':''}`} onClick={()=>setTab('history')}>Workflow History</button>
          </div>

          <div className={`ca-tabpanel ${tab==='results'?'active':''}`} style={{padding:'14px 16px'}}>
            <div className="ca-toolbar">
              <div className="ca-filters">
                <button className={`ca-filter ${filter==='all'?'active':''}`} onClick={()=>setFilter('all')}>All<span className="ca-count">{results.length}</span></button>
                <button className={`ca-filter ${filter==='match'?'active':''}`} onClick={()=>setFilter('match')}>Matched<span className="ca-count">{counts.match}</span></button>
                <button className={`ca-filter ${filter==='mismatch'?'active':''}`} onClick={()=>setFilter('mismatch')}>Mismatched<span className="ca-count">{counts.mismatch}</span></button>
                <button className={`ca-filter ${filter==='missing'?'active':''}`} onClick={()=>setFilter('missing')}>Missing<span className="ca-count">{counts.missing}</span></button>
                <button className={`ca-filter ${filter==='absent'?'active':''}`} onClick={()=>setFilter('absent')}>Not in either<span className="ca-count">{counts.absent}</span></button>
              </div>
              <select className="ca-select" style={{minWidth:220}} value={sectionFilter} onChange={e=>setSectionFilter(e.target.value)}>
                <option value="all">All sections</option>
                {sections.map(s=><option key={s} value={s}>{s}</option>)}
              </select>
              <span style={{flex:1}}/>
              <span style={{fontSize:'.75rem',color:'var(--ca-muted)'}}>
                {remarkCount > 0 && <><strong>{remarkCount}</strong> row{remarkCount===1?'':'s'} annotated · </>}
                {filtered.length} shown
              </span>
            </div>

            <table className="ca-table" style={{border:'1px solid var(--ca-line)',borderRadius:4,overflow:'hidden'}}>
              <thead><tr>
                <th style={{width:'22%'}}>Field</th>
                <th style={{width:'24%'}}>{meta.typeLeft}</th>
                <th style={{width:'24%'}}>{meta.typeRight}</th>
                <th style={{width:90}} className="ca-center">Status</th>
                <th>Analyst Remark</th>
              </tr></thead>
              <tbody>
                {sections.map(sec => grouped[sec] && (
                  <React.Fragment key={sec}>
                    <tr><td colSpan={5} className="ca-group-row">{sec}<span className="ca-count">{grouped[sec].length} field{grouped[sec].length===1?'':'s'}</span></td></tr>
                    {grouped[sec].map((r,i)=>{
                      const key = `${r.sec}-${r.field}`;
                      const delta = r.delta;
                      return (
                        <tr key={key}>
                          <td style={{fontWeight:'bold',color:'var(--ca-ink)'}}>{r.field}</td>
                          <td>
                            <div className={`ca-value ${r.missingSide==='binder'?'empty':''}`}>
                              {r.binder === '—' ? <em>— not present —</em> : r.binder}
                            </div>
                            {r.pageA != null && r.binder !== '—' && <div style={{fontSize:'.6875rem',color:'var(--ca-muted)'}}>page {r.pageA}</div>}
                          </td>
                          <td>
                            <div className={`ca-value ${r.missingSide==='policy'?'empty':''}`}>
                              {r.policy === '—' ? <em>— not present —</em> : r.policy}
                            </div>
                            {r.pageB != null && r.policy !== '—' && <div style={{fontSize:'.6875rem',color:'var(--ca-muted)'}}>page {r.pageB}</div>}
                            {delta && <div style={{fontSize:'.6875rem',color:'var(--ca-bad)',fontWeight:'bold',marginTop:2}}>Δ {delta}</div>}
                          </td>
                          <td className="ca-center">
                            {r.status==='match' && <span className="ca-badge ca-badge--ok"><Icon name="check" size={14}/>Match</span>}
                            {r.status==='mismatch' && <span className="ca-badge ca-badge--bad"><Icon name="x" size={14}/>Mismatch</span>}
                            {r.status==='missing' && !r.absent && <span className="ca-badge ca-badge--warn"><Icon name="alert" size={14}/>Missing</span>}
                            {r.status==='missing' && r.absent && <span className="ca-badge ca-badge--neutral"><Icon name="minus" size={14}/>Not in either</span>}
                          </td>
                          <td>
                            {r.status==='match' && !r.conflict ? (
                              <span style={{fontSize:'.75rem',color:'var(--ca-muted)',fontStyle:'italic'}}>—</span>
                            ) : (
                              <>
                                {r.conflict && <div style={{fontSize:'.6875rem',color:'#9A6200',fontWeight:'bold',marginBottom:4}}>⚠ Conflict in document: {r.conflict}</div>}
                                {r.status!=='match' && r.note && <div style={{fontSize:'.6875rem',color:'var(--ca-muted)',marginBottom:4}}>{r.note}</div>}
                                <input
                                  className={`ca-remark ${(remarks[key]||{}).text?'has':''}`}
                                  placeholder="Add note for carrier follow-up…"
                                  value={(remarks[key]||{}).text||''}
                                  disabled={approved}
                                  onChange={e=>setRemarkText(key, e.target.value)}
                                />
                                {needsResolution(r) && (
                                  <label style={{display:'flex',alignItems:'center',gap:5,marginTop:4,fontSize:'.6875rem',color:'var(--ca-muted)',cursor:approved?'default':'pointer'}}>
                                    <input type="checkbox" disabled={approved}
                                      checked={!!(remarks[key]||{}).resolved}
                                      onChange={e=>setRemarkResolved(key, e.target.checked)}/>
                                    Resolved
                                  </label>
                                )}
                              </>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </React.Fragment>
                ))}
                {filtered.length === 0 && (
                  <tr><td colSpan={5} style={{padding:'32px',textAlign:'center',color:'var(--ca-muted)',fontStyle:'italic'}}>No rows match the current filter.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className={`ca-tabpanel ${tab==='summary'?'active':''}`} style={{padding:'14px 16px'}}>
            <table className="ca-table" style={{border:'1px solid var(--ca-line)'}}>
              <thead><tr><th>Section</th><th className="ca-center">Fields</th><th className="ca-center">Matched</th><th className="ca-center">Mismatched</th><th className="ca-center">Missing</th><th className="ca-center">Not in either</th><th>Status</th></tr></thead>
              <tbody>
                {sections.map(sec=>{
                  const rows = results.filter(r=>r.sec===sec);
                  const m=rows.filter(r=>r.status==='match').length;
                  const x=rows.filter(r=>r.status==='mismatch').length;
                  const n=rows.filter(r=>r.status==='missing' && !r.absent).length;
                  const a=rows.filter(r=>r.absent).length;
                  return (
                    <tr key={sec} className={x===0 && n===0?'is-clean':''}>
                      <td style={{fontWeight:'bold',color:'var(--ca-ink)'}}>{sec}</td>
                      <td className="ca-center">{rows.length}</td>
                      <td className="ca-center"><span className="ca-badge ca-badge--ok">{m}</span></td>
                      <td className="ca-center">{x>0?<span className="ca-badge ca-badge--bad">{x}</span>:'—'}</td>
                      <td className="ca-center">{n>0?<span className="ca-badge ca-badge--warn">{n}</span>:'—'}</td>
                      <td className="ca-center">{a>0?<span className="ca-badge ca-badge--neutral">{a}</span>:'—'}</td>
                      <td>{x===0 && n===0 ? <span className="ca-badge ca-badge--ok">Clean</span> : <span className="ca-badge ca-badge--info">Needs review</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className={`ca-tabpanel ${tab==='docs'?'active':''}`} style={{padding:'14px 16px'}}>
            <div className="ca-grid-2 ca-keep" style={{marginBottom:14}}>
              {[{d:meta.docLeft,t:meta.typeLeft},{d:meta.docRight,t:meta.typeRight}].map((x,i)=>(
                <div key={i} style={{background:'#fff',border:'1px solid var(--ca-line)',borderRadius:4,padding:14}}>
                  <div style={{fontSize:'.5625rem',fontWeight:'bold',letterSpacing:'.07em',textTransform:'uppercase',color:'var(--ca-muted)'}}>{x.t}</div>
                  <div style={{fontSize:'.9375rem',fontWeight:'bold',color:'var(--ca-ink)',marginTop:3}}>{x.d?.name}</div>
                  <div style={{fontSize:'.75rem',color:'var(--ca-muted)'}}>{x.d?.pages} page{x.d?.pages===1?'':'s'}</div>
                </div>
              ))}
            </div>
            <SectionHead title="Line-by-Line Differences" sub="Red = only in the left document, green = only in the right"/>
            <DocDiffView diff={meta.docDiff} typeLeft={meta.typeLeft} typeRight={meta.typeRight}
              pagesLeft={meta.docLeft?.pages} pagesRight={meta.docRight?.pages}/>
          </div>

          <div className={`ca-tabpanel ${tab==='log'?'active':''}`} style={{padding:'14px 16px'}}>
            <table className="ca-table" style={{border:'1px solid var(--ca-line)'}}>
              <tbody>
                <tr><td style={{width:'30%',color:'var(--ca-muted)'}}>Run ID</td><td style={{fontWeight:'bold'}}>{meta.runId||'—'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Account</td><td style={{fontWeight:'bold'}}>{meta.account||'—'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Left Document</td><td>{meta.docLeft?.name} ({meta.typeLeft})</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Right Document</td><td>{meta.docRight?.name} ({meta.typeRight})</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Checklists Applied</td><td>{appliedText}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Fields Checked</td><td>{results.length}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Model</td><td>{modelName}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>How results were decided</td><td>{u && u.mode === 'extract' ? 'Model extracts values with pages; fixed rules compare them' : u && u.mode === 'judge' ? 'Model extracts and judges' : 'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Completed</td><td>{meta.date||'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Run Owner</td><td>{meta.runOwner||'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Policy Effective</td><td>{meta.policyEffective||'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Input tokens</td><td>{tok(u && u.input_tokens)}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Output tokens</td><td>{tok(u && u.output_tokens)}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Thinking tokens</td><td>{tok(u && u.thinking_tokens)}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Total tokens</td><td style={{fontWeight:'bold'}}>{tok(u && u.total_tokens)}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Est. model cost</td><td>{costText}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Processing time</td><td>{u ? fmtDur(u.latency_s) : 'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>of which reading the PDFs</td><td>{u && u.parse_s != null ? fmtDur(u.parse_s) : 'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>of which the model call</td><td>{u && u.model_s != null ? fmtDur(u.model_s) : 'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Model attempts</td><td>{u && u.attempts ? (u.attempts > 1 ? `${u.attempts} (retried after an incomplete first answer)` : '1') : 'Not recorded'}</td></tr>
                <tr><td style={{color:'var(--ca-muted)'}}>Text truncated</td><td>{cut === null ? 'Not recorded' : cut.length ? 'Yes: ' + cut.join(', ') : 'No'}</td></tr>
              </tbody>
            </table>
          </div>

          <div className={`ca-tabpanel ${tab==='history'?'active':''}`} style={{padding:'14px 16px'}}>
            <WorkflowHistoryTimeline meta={meta}/>
          </div>
        </div>

        {approved ? (
          <Verdict kind="suc" icon="✓" title="Approved">
            Approved by {meta.approval.approvedBy} on {meta.approval.approvedAt}. Remarks are locked.
          </Verdict>
        ) : meta.rejection ? (
          <Verdict kind="dng" icon="✕" title={`Rejected by ${meta.rejection.rejectedBy} on ${meta.rejection.rejectedAt}`}>
            {meta.rejection.reason || 'No reason given.'} Save updated remarks to address the feedback — that automatically moves this back to In Review.
          </Verdict>
        ) : versions.length > 0 && (
          <div className="ca-panel is-wide" style={{padding:'10px 16px',fontSize:'.75rem',color:'var(--ca-muted)'}}>
            Remarks saved: {plural(versions.length,'version')}. Latest — V{versions[versions.length-1].version} by {versions[versions.length-1].savedBy}, {versions[versions.length-1].savedAt}.
          </div>
        )}

        {saveError && <Verdict kind="dng" icon="✕" title="Could not save remarks">{saveError}</Verdict>}
        {approveError && <Verdict kind="dng" icon="✕" title="Could not approve">{approveError}</Verdict>}
        {rejectError && <Verdict kind="dng" icon="✕" title="Could not reject">{rejectError}</Verdict>}

        {showRejectBox && !approved && (
          <div className="ca-panel is-wide" style={{padding:'12px 16px'}}>
            <label className="ca-label">Reason for rejecting (shown to the reviewer)</label>
            <input className="ca-input" value={rejectReason} onChange={e=>setRejectReason(e.target.value)}
              placeholder="What needs to change before this can be approved?" style={{marginBottom:8}}/>
            <div style={{display:'flex',gap:8,justifyContent:'flex-end'}}>
              <button className="ca-btn is-quiet is-small" onClick={()=>{setShowRejectBox(false); setRejectReason('');}}>Cancel</button>
              <button className="ca-btn is-small" style={{background:'var(--ca-bad,#B2362B)',color:'#fff'}} onClick={rejectRun} disabled={rejecting}>
                {rejecting ? 'Rejecting…' : 'Confirm Reject'}
              </button>
            </div>
          </div>
        )}

        <div style={{display:'flex',gap:8,justifyContent:'flex-end',marginTop:6,alignItems:'center'}}>
          {!approved && needing.length > 0 && (
            <span style={{fontSize:'.75rem',color:'var(--ca-muted)',marginRight:'auto'}}>
              {unresolvedCount === 0 ? 'All flagged fields marked resolved.' : `${unresolvedCount} of ${plural(needing.length,'flagged field')} still unresolved.`}
            </span>
          )}
          {!approved && (
            <button className="ca-btn is-quiet" onClick={saveRemarks} disabled={saving}>{saving ? 'Saving…' : 'Save Remarks'}</button>
          )}
          {me && me.isAdmin && !approved && !showRejectBox && (
            <button className="ca-btn is-quiet" onClick={()=>setShowRejectBox(true)}>Reject</button>
          )}
          {me && me.isAdmin && !approved && (
            <button className="ca-btn is-primary" onClick={approveRun} disabled={approving || unresolvedCount > 0}
              title={unresolvedCount > 0 ? `${unresolvedCount} flagged field(s) must be marked resolved first` : ''}>
              {approving ? 'Approving…' : 'Approve'}
            </button>
          )}
          {me && !me.isAdmin && !approved && (
            <span style={{fontSize:'.75rem',color:'var(--ca-muted)',fontStyle:'italic'}}>Only admin accounts can approve or reject a run.</span>
          )}
          <button className="ca-btn is-quiet" onClick={exportCsv}>Export CSV</button>
          <button className="ca-btn is-quiet" onClick={()=>onGoto('dashboard')}>Back to Dashboard</button>
          <button className="ca-btn is-quiet" onClick={onNew}>+ New Comparison</button>
        </div>
      </div>
    </>
  );
}

/* ---------------- CHECKLISTS LIST (read-only) ---------------- */
function ChecklistsScreen({ checklists=[], checklistsError=null, onView }){
  const [q, setQ] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const types = [...new Set(checklists.map(t=>t.type))];

  const filtered = checklists.filter(t => {
    if (typeFilter !== 'all' && t.type !== typeFilter) return false;
    if (q && !t.name.toLowerCase().includes(q.toLowerCase())) return false;
    return true;
  });

  return (
    <>
      <div className="ca-pagehead">
        <div className="ca-kicker">Checklists</div>
        <h2>Checklists — {checklists.length} Available</h2>
        <p className="ca-lede">Each checklist is a set of fields the comparison checks. A run compares exactly the fields of the checklists selected on New Comparison. In this MVP the checklists are defined on the server and are read-only here.</p>
        <div className="ca-tags">
          <Chip kind="ok">{plural(checklists.reduce((a,t)=>a+t.fieldCount,0),'field')} across all checklists</Chip>
        </div>
      </div>

      <div className="ca-body">
        <SectionHead title="All Checklists"/>
        <div className="ca-panel is-wide">
          <div className="ca-panel-body" style={{display:'flex',gap:10,alignItems:'center',borderBottom:'1px solid var(--ca-line)',paddingBottom:12,marginBottom:0}}>
            <input className="ca-input" placeholder="Search checklists by name…" style={{flex:1,maxWidth:360}} value={q} onChange={e=>setQ(e.target.value)}/>
            <div className="ca-filters">
              <button className={`ca-filter ${typeFilter==='all'?'active':''}`} onClick={()=>setTypeFilter('all')}>All types</button>
              {types.map(t=><button key={t} className={`ca-filter ${typeFilter===t?'active':''}`} onClick={()=>setTypeFilter(t)}>{t}</button>)}
            </div>
          </div>

          {checklistsError && (
            <div style={{padding:'16px',color:'var(--ca-bad)',fontSize:'.8125rem'}}>{checklistsError}</div>
          )}

          <table className="ca-table" style={{marginTop:0}}>
            <thead><tr>
              <th>Checklist</th><th>Type</th><th className="ca-center">Fields</th><th>Status</th><th></th>
            </tr></thead>
            <tbody>
              {filtered.map(t=>(
                <tr key={t.id}>
                  <td>
                    <div style={{fontWeight:'bold',color:'var(--ca-ink)'}}>{t.name}</div>
                    <div style={{fontSize:'.6875rem',color:'var(--ca-muted)'}}>{t.desc}</div>
                  </td>
                  <td><span className="ca-badge ca-badge--info">{t.type}</span></td>
                  <td className="ca-center" style={{fontWeight:'bold'}}>{t.fieldCount}</td>
                  <td><span className="ca-badge ca-badge--ok">{t.status}</span></td>
                  <td style={{textAlign:'right'}}><button className="ca-btn is-quiet is-small" onClick={()=>onView(t)}>View →</button></td>
                </tr>
              ))}
              {filtered.length === 0 && !checklistsError && (
                <tr><td colSpan={5} style={{padding:'28px',textAlign:'center',color:'var(--ca-muted)',fontStyle:'italic'}}>No checklists to show.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

/* ---------------- CHECKLIST VIEWER (MODAL, read-only) ---------------- */
function ChecklistViewModal({ checklist, onClose }){
  return (
    <Modal
      wide
      title={checklist.name}
      onClose={onClose}
      footer={<button className="ca-btn is-quiet" onClick={onClose}>Close</button>}
    >
      <div style={{fontSize:'.8125rem',color:'var(--ca-ink)',marginBottom:4}}>{checklist.desc}</div>
      <div style={{fontSize:'.75rem',color:'var(--ca-muted)',marginBottom:12}}>Applies to: {checklist.lineLabel || 'Any policy'}</div>

      <h4 style={{margin:'14px 0 8px',fontSize:'.75rem',fontWeight:'bold',color:'var(--ca-ink)',letterSpacing:'.05em',textTransform:'uppercase'}}>
        Fields ({checklist.fieldCount})
      </h4>
      <div style={{border:'1px solid var(--ca-line)',borderRadius:4,overflow:'hidden'}}>
        <table className="ca-table" style={{marginTop:0}}>
          <thead><tr><th>Section</th><th>Field</th></tr></thead>
          <tbody>
            {checklist.fields.map(f=>(
              <tr key={f.section+'|'+f.field}>
                <td style={{color:'var(--ca-muted)'}}>{f.section}</td>
                <td style={{fontWeight:'bold',color:'var(--ca-ink)'}}>{f.field}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {checklist.guidance && (
        <>
          <h4 style={{margin:'14px 0 8px',fontSize:'.75rem',fontWeight:'bold',color:'var(--ca-ink)',letterSpacing:'.05em',textTransform:'uppercase'}}>Reading guidance sent to the model</h4>
          <div style={{fontSize:'.8125rem',color:'var(--ca-muted)',lineHeight:1.5}}>{checklist.guidance}</div>
        </>
      )}
    </Modal>
  );
}

/* ---------------- RUN HISTORY ---------------- */
function HistoryScreen({ runs, onOpen, firestoreStatus, me, historyScope, setHistoryScope }){
  const [q, setQ] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const filtered = runs.filter(r => {
    if (q && !(r.account || '').toLowerCase().includes(q.toLowerCase())) return false;
    if (statusFilter !== 'all' && (r.reviewStatus || 'new') !== statusFilter) return false;
    return true;
  });
  const isAdmin = me && me.isAdmin;
  return (
    <>
      <div className="ca-pagehead">
        <div className="ca-kicker">Run History</div>
        <h2>Run History — {plural(runs.length,'Comparison')}</h2>
        <p className="ca-lede">{historyScope==='team' ? 'Every comparison across the whole team' : 'Your own comparisons'}, with its result summary, fields checked and token usage. Per-run usage is also written to Cloud Logging.</p>
        <div className="ca-tags">
          {firestoreStatus === 'connected'
            ? <Chip kind="ok">Saved permanently</Chip>
            : <Chip kind="warn">In-memory · resets on redeploy</Chip>}
          {me && me.email && <Chip kind="neutral">{historyScope==='team' ? 'Whole team' : 'Your runs only'}</Chip>}
        </div>
      </div>
      <div className="ca-body">
        <SectionHead title="All Runs" right={isAdmin && (
          <div className="ca-filters">
            <button className={`ca-filter ${historyScope!=='team'?'active':''}`} onClick={()=>setHistoryScope('mine')}>My runs</button>
            <button className={`ca-filter ${historyScope==='team'?'active':''}`} onClick={()=>setHistoryScope('team')}>Whole team</button>
          </div>
        )}/>
        <div className="ca-panel is-wide">
          <div className="ca-panel-body" style={{borderBottom:'1px solid var(--ca-line)',paddingBottom:12,display:'flex',gap:10,alignItems:'center'}}>
            <input className="ca-input" placeholder="Search by account…" style={{flex:1,maxWidth:360}} value={q} onChange={e=>setQ(e.target.value)}/>
            <div className="ca-filters">
              {[['all','All'],['new','New'],['in_review','In Review'],['rejected','Rejected'],['approved','Approved']].map(([k,l])=>(
                <button key={k} className={`ca-filter ${statusFilter===k?'active':''}`} onClick={()=>setStatusFilter(k)}>{l}</button>
              ))}
            </div>
          </div>
          <table className="ca-table" style={{marginTop:0}}>
            <thead><tr>
              <th>Run</th><th>Account / Documents</th><th>Date / Owner</th><th>Status</th><th className="ca-center">Fields</th>
              <th className="ca-center">Matched</th><th className="ca-center">Mismatched</th><th className="ca-center">Missing</th><th className="ca-center">Tokens</th><th></th>
            </tr></thead>
            <tbody>
              {filtered.map(r=>(
                <tr key={r.id}>
                  <td style={{fontFamily:'monospace',fontSize:'.75rem',color:'var(--ca-primary)'}}>{r.id}</td>
                  <td>
                    <div className="ca-run-title">{r.account}</div>
                    <div className="ca-run-sub">{r.binder} ↔ {r.policy}</div>
                  </td>
                  <td><div>{r.date}</div><div className="ca-run-sub">{r.user}</div></td>
                  <td><StatusBadge status={r.reviewStatus}/></td>
                  <td className="ca-center">{r.fieldCount != null ? r.fieldCount : '—'}</td>
                  <td className="ca-center"><span className="ca-badge ca-badge--ok">{r.matched}</span></td>
                  <td className="ca-center">{r.mismatched>0?<span className="ca-badge ca-badge--bad">{r.mismatched}</span>:'—'}</td>
                  <td className="ca-center">{r.missing>0?<span className="ca-badge ca-badge--warn">{r.missing}</span>:'—'}</td>
                  <td className="ca-center">{r.usage ? fmtTok(r.usage.total_tokens) : '—'}</td>
                  <td style={{textAlign:'right'}}><button className="ca-btn is-quiet is-small" onClick={()=>onOpen(r)}>Open →</button></td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={10} style={{padding:'28px',textAlign:'center',color:'var(--ca-muted)',fontStyle:'italic'}}>No runs to show.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}


// Styles for elements the page stylesheet does not cover (status badges, section headers,
// note boxes, toolbar). Added once at load; nothing in index.html needs to change.
(function addStyles(){
  if (typeof document === 'undefined' || document.getElementById('ca-extra-styles')) return;
  const st = document.createElement('style');
  st.id = 'ca-extra-styles';
  st.textContent = `
.eta{display:inline-block;padding:2px 9px;border-radius:10px;font-size:.6875rem;font-weight:bold;line-height:1.5;white-space:nowrap}
.ematch,.edone{background:#DDF1E7;color:#1B7A55}
.emiss{background:#F8E1DE;color:#B2362B}
.emissing{background:#FCEFD2;color:#9A6200}
.epending{background:#E7EAEA;color:#5E6B70}
.ereview{background:#DCEBEA;color:#1D2B33}
.sec-header{background:#EEF3F2;color:#1D2B33;font-weight:bold;font-size:.75rem;letter-spacing:.03em;text-transform:uppercase;padding:8px 12px}
.sec-header .n{float:right;font-weight:normal;text-transform:none;letter-spacing:0;color:#5E6B70}
.remark-inp{width:100%;box-sizing:border-box;padding:5px 8px;border:1px solid #D6DCDB;border-radius:3px;font:inherit;font-size:.75rem}
.remark-inp.has{border-color:#1B7A55}
.res-toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.run-row-title{font-weight:bold;color:#1D2B33}
.run-row-sub{font-size:.6875rem;color:#5E6B70}
.modal-ft{display:flex;justify-content:flex-end;gap:8px;padding:12px 16px;border-top:1px solid #D6DCDB}
.btn.sm{padding:4px 10px;font-size:.75rem}
`;
  document.head.appendChild(st);
})();


/* ---------------- ADMIN ---------------- */
function AdminScreen({ onGoto }){
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(()=>{
    fetch('/api/admin/stats')
      .then(res => { if (!res.ok) throw new Error(res.status === 403 ? 'Admin access required.' : 'Could not load admin stats.'); return res.json(); })
      .then(setStats)
      .catch(e => setError(e.message));
  }, []);

  const costLabel = n => n == null ? 'Rate not set' : '$' + n.toFixed(4);

  return (
    <>
      <div className="ca-pagehead">
        <div className="ca-kicker">Admin</div>
        <h2>Team Usage &amp; Cost</h2>
        <p className="ca-lede">Aggregated across every run the team has made. Visible only to admin accounts.</p>
        <div className="ca-tags"><Chip kind="neutral">Admin-only view</Chip></div>
      </div>

      <div className="ca-body">
        {error && <Verdict kind="dng" icon="✕" title="Could not load admin data">{error}</Verdict>}

        {!error && !stats && (
          <div className="ca-panel is-wide"><div className="ca-panel-body" style={{color:'var(--ca-muted)',fontStyle:'italic'}}>Loading…</div></div>
        )}

        {stats && (
          <>
            <div className="ca-grid-4" style={{marginBottom:14}}>
              <StatCard label="Total Runs" value={stats.totalRuns} sub="Across the whole team"/>
              <StatCard label="Total Tokens" value={fmtTok(stats.totalTokens)} sub="Input + output + thinking"/>
              <StatCard label="Total Est. Cost" value={costLabel(stats.totalCost)} sub="Model tokens only"/>
              <StatCard label="People Active" value={stats.byUser.length} sub="With at least one run"/>
            </div>

            <SectionHead title="Review Workflow" sub="Where every run currently stands"/>
            <div className="ca-grid-4" style={{marginBottom:14}}>
              <StatCard label="New" value={stats.byStatus.new} sub="Not started yet" tone="wrn"/>
              <StatCard label="In Review" value={stats.byStatus.in_review} sub="Remarks in progress"/>
              <StatCard label="Rejected" value={stats.byStatus.rejected} sub="Sent back for more work" tone="dng"/>
              <StatCard label="Approved" value={stats.byStatus.approved} sub="Complete" tone="suc"/>
            </div>

            <SectionHead title="By Person" sub="Sorted by number of runs" right={
              <button className="ca-btn is-quiet is-small" onClick={()=>onGoto('history')}>View all runs →</button>
            }/>
            <div className="ca-panel is-wide">
              <table className="ca-table" style={{marginTop:0}}>
                <thead><tr>
                  <th>Person</th><th className="ca-center">Runs</th><th className="ca-center">Tokens</th>
                  <th className="ca-center">Est. cost</th><th className="ca-center">Avg processing time</th>
                </tr></thead>
                <tbody>
                  {stats.byUser.map(b=>(
                    <tr key={b.email}>
                      <td style={{fontWeight:'bold',color:'var(--ca-ink)',wordBreak:'break-all'}}>{b.email}</td>
                      <td className="ca-center">{b.runs}</td>
                      <td className="ca-center">{fmtTok(b.tokens)}</td>
                      <td className="ca-center">{costLabel(b.cost)}</td>
                      <td className="ca-center">{b.avgLatencyS != null ? fmtDur(b.avgLatencyS) : '—'}</td>
                    </tr>
                  ))}
                  {stats.byUser.length === 0 && (
                    <tr><td colSpan={5} style={{padding:'28px',textAlign:'center',color:'var(--ca-muted)',fontStyle:'italic'}}>No runs yet.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </>
  );
}


/* ---------------- LOGIN (test accounts — a stand-in for SSO/IAP) ---------------- */
function LoginScreen({ onLoggedIn }){
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function submit(e){
    e.preventDefault();
    if (busy) return;
    setBusy(true); setError(null);
    fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ username, password }),
    })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Could not sign in.');
        return data;
      })
      .then(onLoggedIn)
      .catch(e => setError(e.message))
      .finally(() => setBusy(false));
  }

  return (
    <div style={{minHeight:'100vh',display:'flex',alignItems:'center',justifyContent:'center',background:'var(--ca-ink,#1D2B33)'}}>
      <form onSubmit={submit} style={{background:'#fff',borderRadius:6,padding:'32px 28px',width:320,boxShadow:'0 8px 30px rgba(0,0,0,.25)'}}>
        <div style={{fontSize:'1.125rem',fontWeight:'bold',color:'var(--ca-ink)',marginBottom:2}}>Checking Agent</div>
        <div style={{fontSize:'.75rem',color:'var(--ca-muted)',marginBottom:20}}>Sign in with a test account — not for real client data yet.</div>
        <div className="ca-field" style={{marginBottom:12}}>
          <label className="ca-label">Username</label>
          <input className="ca-input" autoFocus autoCapitalize="off" autoCorrect="off" value={username} onChange={e=>setUsername(e.target.value)}/>
        </div>
        <div className="ca-field" style={{marginBottom:16}}>
          <label className="ca-label">Password</label>
          <input className="ca-input" type="password" value={password} onChange={e=>setPassword(e.target.value)}/>
        </div>
        {error && <div style={{color:'var(--ca-bad,#B2362B)',fontSize:'.75rem',marginBottom:14}}>{error}</div>}
        <button className="ca-btn is-primary" type="submit" disabled={busy} style={{width:'100%'}}>{busy ? 'Signing in…' : 'Sign in'}</button>
      </form>
    </div>
  );
}

Object.assign(window, { DashboardScreen, NewRunScreen, ProcessingScreen, ResultsScreen, ChecklistsScreen, ChecklistViewModal, HistoryScreen, AdminScreen, LoginScreen, selectedLines, buildCsv });
