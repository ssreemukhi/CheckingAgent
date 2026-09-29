// Main app — navigation and state

const { useState, useEffect, useRef } = React;

/* Convert a backend run record into the row shape used by Dashboard / History */
function toRunRow(r){
  return {
    id: r.id,
    account: r.account,
    binder: r.docLeft?.name,
    policy: r.docRight?.name,
    date: r.date,
    user: r.runOwner || 'Not recorded',
    matched: r.matched,
    mismatched: r.mismatched,
    missing: r.missing,
    status: r.status,
    reviewStatus: r.reviewStatus || 'new',
    usage: r.usage || null,
    fieldCount: r.fieldCount != null ? r.fieldCount : (r.usage ? r.usage.field_count : null),
  };
}

function Sidebar({ current, onGoto, counts, me, onSignOut }){
  const items = [
    {id:'dashboard',   label:'Dashboard',        ic:'grid'},
    {id:'new',         label:'New Comparison',   ic:'newdoc'},
    {id:'history',     label:'Run History',      ic:'clock', count:counts.history},
    {id:'checklists',  label:'Checklists',       ic:'list',  count:counts.checklists},
  ];
  const isAdmin = me && me.isAdmin;
  const initial = me && me.email ? me.email.charAt(0).toUpperCase() : '';
  return (
    <>
      <header className="ca-topbar">
        <div className="ca-brand">
          <span className="ca-brand-mark"><Icon name="compare" size={26}/></span>
          <div>
            <div className="ca-brand-name">Checking Agent</div>
            <div className="ca-muted">Insurance document comparison</div>
          </div>
        </div>

        {me && me.email && (
          <div className="ca-account">
            <span className="ca-avatar" aria-hidden="true">{initial}</span>
            <div className="ca-account-id">
              <div className="ca-account-email">{me.email}</div>
              <div className="ca-account-role">
                {isAdmin ? 'Administrator' : 'Reviewer'}
                {!me.iapVerified && <span title="IAP not fully set up"> · test sign-in</span>}
              </div>
            </div>
            {onSignOut && <button className="ca-signout" onClick={()=>onSignOut()} title="Sign out"><Icon name="signout" size={18}/><span>Sign out</span></button>}
          </div>
        )}
      </header>

      <aside className="ca-sidenav">
        <nav className="ca-nav" aria-label="Main">
          {items.map(i=>(
            <button key={i.id} className={`ca-navlink ${current===i.id?'active':''}`} onClick={()=>onGoto(i.id)} aria-current={current===i.id?'page':undefined}>
              <Icon name={i.ic} size={22} className="ca-navlink-icon"/>
              <span className="ca-navlink-label">{i.label}</span>
              {i.count!=null && <span className="ca-navlink-count">{i.count}</span>}
            </button>
          ))}
          {isAdmin && (
            <>
              <div className="ca-nav-divider" role="separator"></div>
              <button className={`ca-navlink ${current==='admin'?'active':''}`} onClick={()=>onGoto('admin')} aria-current={current==='admin'?'page':undefined}>
                <Icon name="shield" size={22} className="ca-navlink-icon"/>
                <span className="ca-navlink-label">Admin</span>
              </button>
            </>
          )}
        </nav>
      </aside>
    </>
  );
}

function App(){
  const [screen, setScreen] = useState('dashboard');
  const [checklists, setChecklists] = useState([]);
  const [checklistsError, setChecklistsError] = useState(null);
  const [viewing, setViewing] = useState(null);
  const [runs, setRuns] = useState([]);
  const [runMeta, setRunMeta] = useState(null);
  const [toast, setToast] = useState(null);
  const [firestoreStatus, setFirestoreStatus] = useState(null); // null = not known yet
  const [me, setMe] = useState(null); // {email, isAdmin, iapVerified} — null until /api/me answers
  const [historyScope, setHistoryScope] = useState('mine'); // 'mine' | 'team' (team only ever used by admins)

  // Whether run history / ROI inputs are durably stored (Firestore) or not (this
  // process's memory / this browser only) — shown so the app never overstates what
  // it can actually promise. Checked once; if it fails, the app just assumes not durable,
  // which is always the safe default.
  useEffect(()=>{
    fetch('/health')
      .then(res => res.json())
      .then(d => setFirestoreStatus(d.firestore || 'unknown'))
      .catch(() => setFirestoreStatus('unknown'));
  }, []);

  // Whenever the signed-in identity changes — logging in, logging out, or switching
  // test accounts — drop back to the dashboard and forget whatever was on screen.
  // Without this, a Results page fetched under one identity (e.g. admin looking at
  // someone's run) would keep sitting there, still fully rendered, after switching to
  // a different account — not a new unauthorized fetch, but a stale one lingering
  // somewhere it shouldn't appear to. Skipped on the very first render (prevEmail
  // starts as undefined) so a normal page load doesn't bounce to the dashboard.
  const prevEmailRef = useRef(undefined);
  useEffect(()=>{
    const email = me ? me.email : undefined;
    if (prevEmailRef.current !== undefined && prevEmailRef.current !== email) {
      setScreen('dashboard');
      setRunMeta(null);
    }
    prevEmailRef.current = email;
  }, [me && me.email]);

  useEffect(()=>{
    fetch('/api/me')
      .then(res => res.json())
      .then(setMe)
      .catch(() => setMe({email: null, isAdmin: false, iapVerified: false}));
  }, []);

  // Checklists are defined on the server; the app only lists them.
  useEffect(()=>{
    fetch('/api/checklists')
      .then(res => { if (!res.ok) throw new Error('bad response'); return res.json(); })
      .then(data => setChecklists(Array.isArray(data) ? data : []))
      .catch(() => setChecklistsError('Could not load the checklists from the server. Refresh the page to try again.'));
  }, []);

  // Load run history from the backend. Refetches whenever the admin switches between
  // 'my runs' and the team view, AND whenever the signed-in identity changes (login,
  // logout, switching test accounts) — without the second dependency, the page's very
  // first fetch (which runs before /api/me has resolved, so it goes out with no session
  // yet and gets the unscoped 'no identity' fallback list) would sit there stale forever
  // after someone logs in, since nothing else would ever tell it to ask again. The scope
  // actually enforced is always decided server-side from the caller's identity — this is
  // only which view was asked for.
  useEffect(()=>{
    const qs = historyScope === 'team' ? '?scope=team' : '';
    fetch('/api/history' + qs)
      .then(res => res.json())
      .then(data => setRuns(data.map(toRunRow)))
      .catch(() => {});
  }, [historyScope, me && me.email]);

  // Persist cur screen — but never restore into a screen that depends on
  // runMeta (processing/results), since runMeta itself is never persisted.
  useEffect(()=>{
    const s = localStorage.getItem('ca:screen');
    const safeScreens = ['dashboard', 'new', 'history', 'checklists'];
    if (s && safeScreens.includes(s)) setScreen(s);
  },[]);
  useEffect(()=>{ localStorage.setItem('ca:screen', screen); },[screen]);

  function startNewRun(){ setScreen('new'); }

  function onProcess(meta){
    const formData = new FormData();
    formData.append('fileLeft', meta.docLeft.file);
    formData.append('fileRight', meta.docRight.file);
    formData.append('account', meta.account || '');
    formData.append('typeLeft', meta.typeLeft);
    formData.append('typeRight', meta.typeRight);
    formData.append('runOwner', meta.runOwner || '');
    formData.append('policyEffective', meta.policyEffective || '');
    // The server compares exactly the fields of the checklists sent here.
    formData.append('checklists', JSON.stringify(meta.selected || []));
    if (meta.idData) formData.append('idData', meta.idData);  // optional, raw JSON text; server ignores it if malformed

    const promise = fetch('/api/compare', { method: 'POST', body: formData })
      .then(async res => {
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Comparison failed.');
        return data;
      });

    setRunMeta({ ...meta, resultPromise: promise });
    setScreen('processing');
  }

  function onProcessingDone(realRun){
    // Functional updates: this callback is captured once by ProcessingScreen's
    // effect, so it must not rely on the runs/runMeta values from that render.
    setRuns(prev => [toRunRow(realRun), ...prev]);
    setRunMeta(prev => ({
      ...prev,
      runId: realRun.id,
      account: realRun.account,
      docLeft: realRun.docLeft,
      docRight: realRun.docRight,
      date: realRun.date,
      usage: realRun.usage || null,
      checklists: realRun.checklists || [],
      fieldCount: realRun.fieldCount,
      docDiff: realRun.docDiff || null,
      identityCheck: realRun.identityCheck || null,
      remarkVersions: realRun.remarkVersions || [],
      approval: realRun.approval || null,
      rejection: realRun.rejection || null,
      rejectionHistory: realRun.rejectionHistory || [],
      reviewStatus: realRun.reviewStatus || 'new',
      runOwner: realRun.runOwner || prev?.runOwner,
      policyEffective: realRun.policyEffective || prev?.policyEffective,
      results: realRun.results,
    }));
    setScreen('results');
  }

  function openRun(r){
    fetch(`/api/history/${r.id}`)
      .then(res => res.json())
      .then(full => {
        if (full.error) throw new Error(full.error);
        setRunMeta({
          runId: full.id, account: full.account,
          docLeft: full.docLeft, docRight: full.docRight,
          typeLeft: full.docLeft?.type, typeRight: full.docRight?.type,
          date: full.date,
          runOwner: full.runOwner,
          policyEffective: full.policyEffective,
          usage: full.usage || null,
          checklists: full.checklists || [],
          fieldCount: full.fieldCount,
          docDiff: full.docDiff || null,
          identityCheck: full.identityCheck || null,
          remarkVersions: full.remarkVersions || [],
          approval: full.approval || null,
          rejection: full.rejection || null,
          rejectionHistory: full.rejectionHistory || [],
          reviewStatus: full.reviewStatus || 'new',
          results: full.results,
        });
        setScreen('results');
      })
      .catch(() => setToast('Could not load that run — it may be from before the last restart.'));
  }

  const results = runMeta?.results || [];

  // Average processing time of the runs measured so far (empty after a redeploy).
  const timed = runs.filter(r => r.usage && r.usage.latency_s);
  const typicalSeconds = timed.length ? timed.reduce((a, r) => a + r.usage.latency_s, 0) / timed.length : null;

  // Test login (a stand-in for SSO/IAP): block the rest of the app until someone signs
  // in. This is a UX gate, not the real security boundary — real access control is
  // Cloud Run's invoker policy / IAP, same as always. Nothing renders here until /api/me
  // has answered (me starts null), so this never flashes the login screen unnecessarily.
  if (me && me.testLoginAvailable && !me.email) {
    return <LoginScreen onLoggedIn={setMe}/>;
  }

  return (
    <>
      <div className="ca-app">
        <Sidebar
          current={screen}
          onGoto={setScreen}
          counts={{history:runs.length, checklists:checklists.length}}
          me={me}
          onSignOut={me && me.testLoginAvailable ? ()=>{
            fetch('/api/logout', {method:'POST'}).finally(()=>setMe({email:null, isAdmin:false, iapVerified:false, testLoginAvailable:true}));
          } : null}
        />
        <main className="ca-page">
          {screen==='dashboard' && <DashboardScreen runs={runs} onNewRun={startNewRun} onOpenRun={openRun} onGoto={setScreen} firestoreStatus={firestoreStatus} me={me}/>}
          {screen==='new' && <NewRunScreen checklists={checklists} checklistsError={checklistsError} onProcess={onProcess} onCancel={()=>setScreen('dashboard')} recentAccounts={[...new Set(runs.map(r=>r.account).filter(Boolean))]} me={me}/>}
          {screen==='processing' && <ProcessingScreen account={runMeta?.account} typeLeft={runMeta?.typeLeft} typeRight={runMeta?.typeRight} onDone={onProcessingDone} resultPromise={runMeta?.resultPromise} typicalSeconds={typicalSeconds}/>}
          {screen==='results' && runMeta && <ResultsScreen
            results={results}
            meta={runMeta}
            me={me}
            onNew={()=>setScreen('new')}
            onGoto={setScreen}
            onRunUpdated={patch => setRunMeta(prev => prev ? {...prev, ...patch} : prev)}
          />}
          {screen==='checklists' && <ChecklistsScreen
            checklists={checklists}
            checklistsError={checklistsError}
            onView={t=>setViewing(t)}
          />}
          {screen==='history' && <HistoryScreen runs={runs} onOpen={openRun} firestoreStatus={firestoreStatus} me={me} historyScope={historyScope} setHistoryScope={setHistoryScope}/>}
          {screen==='admin' && me && me.isAdmin && <AdminScreen onGoto={setScreen}/>}
        </main>
      </div>

      {viewing && (
        <ChecklistViewModal checklist={viewing} onClose={()=>setViewing(null)}/>
      )}


      <Toast msg={toast} onDone={()=>setToast(null)}/>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);
