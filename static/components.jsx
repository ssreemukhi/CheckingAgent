// Reusable UI primitives

const { useState, useEffect, useRef, useMemo } = React;

// Line icons drawn for Checking Agent (24px grid, stroke follows the text colour).
const ICON_PATHS = {
  grid:     'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  compare:  'M4 5h9v13H4zM11 8h9v12h-9zM13.5 14l1.8 1.8 3.2-3.6',
  newdoc:   'M6 3h8l4 4v14H6zM14 3v4h4M12 11v6M9 14h6',
  clock:    'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 7v5l3.5 2',
  list:     'M9 6h11M9 12h11M9 18h11M4 5.5l1 1 2-2M4 11.5l1 1 2-2M4 17.5l1 1 2-2',
  shield:   'M12 3l7 3v6c0 4.5-3 7.5-7 9c-4-1.5-7-4.5-7-9V6zM9 12l2 2 4-4',
  upload:   'M12 16V5M7.5 9.5L12 5l4.5 4.5M5 15v4h14v-4',
  check:    'M5 12.5l4.5 4.5L19 7.5',
  x:        'M6 6l12 12M18 6L6 18',
  alert:    'M12 3.5L21 19H3zM12 10v4M12 16.8v.2',
  minus:    'M6 12h12',
  signout:  'M14 4h5v16h-5M10 8l-4 4 4 4M6 12h9',
  user:     'M12 4a4 4 0 1 0 0 8a4 4 0 1 0 0-8zM4.5 20c1.2-3.6 4-5.5 7.5-5.5s6.3 1.9 7.5 5.5',
};
function Icon({ name, size=16, className='' }){
  const d = ICON_PATHS[name];
  if (!d) return null;
  return (
    <svg className={`ca-icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
      <path d={d}/>
    </svg>
  );
}
// Maps the text glyphs callers already pass to <Verdict icon=…> onto drawn icons.
const CALLOUT_ICONS = {'✓':'check', '!':'alert', '✕':'x'};

function Chip({kind='neutral', children}){
  return <span className={`ca-tag ca-tag--${kind}`}><span className="ca-tag-dot"></span>{children}</span>;
}

function StatCard({label, value, sub, tone}){
  return (
    <div className="ca-stat">
      <div className="ca-stat-label">{label}</div>
      <div className={`ca-stat-value ${tone||''}`}>{value}</div>
      {sub && <div className="ca-stat-note">{sub}</div>}
    </div>
  );
}

function SectionHead({title, sub, right}){
  return (
    <h3 className="ca-section-title">
      <span>{title}</span>
      {sub && <span className="ca-muted">· {sub}</span>}
      <span className="ca-grow"></span>
      {right && <span className="ca-section-aside">{right}</span>}
    </h3>
  );
}

function Widget({title, right, children, padBody=true}){
  return (
    <div className="ca-panel is-wide">
      {(title||right) && (
        <div className="ca-panel-head">
          {title ? <h4>{title}</h4> : <span/>}
          {right}
        </div>
      )}
      {padBody ? <div className="ca-panel-body">{children}</div> : children}
    </div>
  );
}

function Verdict({kind='suc', icon='✓', title, children}){
  return (
    <div className={`ca-callout ca-callout--${kind}`}>
      <div className="ca-callout-icon"><Icon name={CALLOUT_ICONS[icon] || 'alert'} size={20}/></div>
      <div className="ca-callout-text"><h4>{title}</h4><p>{children}</p></div>
    </div>
  );
}

function Modal({title, onClose, children, footer, wide}){
  return (
    <div className="ca-overlay" onClick={onClose}>
      <div className="ca-dialog" onClick={e=>e.stopPropagation()} style={wide?{maxWidth:920}:null}>
        <div className="ca-dialog-head">
          <h3>{title}</h3>
          <button className="ca-close" onClick={onClose}>×</button>
        </div>
        <div className="ca-dialog-body">{children}</div>
        {footer && <div className="ca-dialog-foot">{footer}</div>}
      </div>
    </div>
  );
}

function Toast({msg,onDone}){
  useEffect(()=>{const t=setTimeout(onDone,2600);return()=>clearTimeout(t)},[msg]);
  if(!msg) return null;
  return <div className="ca-toast">{msg}</div>;
}

Object.assign(window,{Icon,Chip,StatCard,SectionHead,Widget,Verdict,Modal,Toast});
