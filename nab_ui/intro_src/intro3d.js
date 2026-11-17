// NAB start-up scenes (three.js). Built with esbuild into ../intro_3d.js (see build.sh). Three styles share one tiny API:
//   NAB3D.supported()                      -> true when WebGL works
//   NAB3D.create(canvas, style, opts)      -> { dispose(), idle(), t() }   style: "particles" | "tunnel" | "aurora"
//   opts: { accent:"#5b8cff", bg:"#0b0c13", onLogo(), onBeat(name), logoAt }
import {
  WebGLRenderer, Scene, PerspectiveCamera, BufferGeometry, Float32BufferAttribute, Points, ShaderMaterial, AdditiveBlending,
  Color, Mesh, PlaneGeometry, TorusGeometry, MeshBasicMaterial, CanvasTexture, DoubleSide, Group, Vector2, LineSegments, FrontSide
} from "three";

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const sstep = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const eio = (t) => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const eout = (t) => 1 - Math.pow(1 - t, 3);
const lerp = (a, b, t) => a + (b - a) * t;
const rnd = (a, b) => a + Math.random() * (b - a);

export function supported() {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl2") || c.getContext("webgl");
    return !!gl;
  } catch (e) { return false; }
}

function hsl(col, dh, ds = 0, dl = 0) { const o = {}; col.getHSL(o); return new Color().setHSL((o.h + dh + 1) % 1, clamp(o.s + ds), clamp(o.l + dl)); }

/* ------------------------------------------------------------------------------------------------------------ particles */
function particlesScene(ctx) {
  const { scene, camera, acc, opts } = ctx;
  camera.position.set(0, 0, 13); camera.fov = 50; camera.updateProjectionMatrix();
  // points that spell NAB
  const W = 1100, H = 360, c = document.createElement("canvas"); c.width = W; c.height = H;
  const g = c.getContext("2d"); g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle";
  g.font = '900 330px Bahnschrift, "Segoe UI Black", "Segoe UI", Arial, sans-serif'; g.fillText("NAB", W / 2, H / 2 + 14);
  const d = g.getImageData(0, 0, W, H).data, pts = [];
  for (let y = 0; y < H; y += 3) for (let x = 0; x < W; x += 3) if (d[(y * W + x) * 4 + 3] > 140) pts.push([(x - W / 2) / W * 9.2, -(y - H / 2) / W * 9.2]);
  for (let i = pts.length - 1; i > 0; i--) { const j = (Math.random() * (i + 1)) | 0; const t = pts[i]; pts[i] = pts[j]; pts[j] = t; }
  const N = Math.min(pts.length, ctx.low ? 3600 : 7200);
  const pos = new Float32Array(N * 3), tgt = new Float32Array(N * 3), rr = new Float32Array(N), sz = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const arm = i % 3, r = Math.pow(Math.random(), .55) * 15, a = r * .8 + arm * 2.094 + rnd(-.35, .35);
    pos[i * 3] = Math.cos(a) * r; pos[i * 3 + 1] = Math.sin(a) * r * .75; pos[i * 3 + 2] = rnd(-5, 4);
    tgt[i * 3] = pts[i][0]; tgt[i * 3 + 1] = pts[i][1]; tgt[i * 3 + 2] = rnd(-.12, .12);
    rr[i] = Math.random(); sz[i] = rnd(.7, 1.7);
  }
  const geo = new BufferGeometry();
  geo.setAttribute("position", new Float32BufferAttribute(pos, 3)); geo.setAttribute("aTarget", new Float32BufferAttribute(tgt, 3));
  geo.setAttribute("aR", new Float32BufferAttribute(rr, 1)); geo.setAttribute("aS", new Float32BufferAttribute(sz, 1));
  const mat = new ShaderMaterial({
    transparent: true, depthWrite: false, blending: AdditiveBlending,
    uniforms: { uT: { value: 0 }, uPx: { value: ctx.px }, uC1: { value: acc }, uC2: { value: hsl(acc, .12, .1, .22) }, uBoom: { value: 0 } },
    vertexShader: `uniform float uT,uPx,uBoom;attribute vec3 aTarget;attribute float aR,aS;varying float vM;varying float vA;
      void main(){
        float p=clamp((uT-.35-aR*.75)/1.9,0.,1.);float e=p*p*(3.-2.*p);e=e*e*(3.-2.*e);
        float ang=uT*(.7+aR*.6)*(1.-e);float c=cos(ang),s=sin(ang);
        vec3 sp=vec3(position.x*c-position.y*s,position.x*s+position.y*c,position.z+sin(uT*1.6+aR*20.)*.35);
        vec3 tp=aTarget+vec3(sin(uT*1.7+aR*40.),cos(uT*1.4+aR*33.),sin(uT*1.1+aR*17.))*.025;
        tp.xy*=1.+uBoom*.10; tp.z+=uBoom*(aR-.5)*1.4;
        vec3 pos=mix(sp,tp,e);
        vec4 mv=modelViewMatrix*vec4(pos,1.);gl_Position=projectionMatrix*mv;
        gl_PointSize=aS*(1.+(1.-e)*.8+uBoom*.9)*uPx*(28./-mv.z);
        vM=aR;vA=.55+.45*e;
      }`,
    fragmentShader: `uniform vec3 uC1,uC2;varying float vM;varying float vA;
      void main(){float d=length(gl_PointCoord-.5);float a=smoothstep(.5,.05,d);if(a<.01)discard;
        vec3 col=mix(uC1,uC2,vM)*1.5+vec3(.35)*smoothstep(.25,.0,d);gl_FragColor=vec4(col,a*vA);}`
  });
  const pts3 = new Points(geo, mat); scene.add(pts3);
  // faint dust for depth
  const M = ctx.low ? 250 : 600, dp = new Float32Array(M * 3);
  for (let i = 0; i < M; i++) { dp[i * 3] = rnd(-22, 22); dp[i * 3 + 1] = rnd(-12, 12); dp[i * 3 + 2] = rnd(-14, 4); }
  const dg = new BufferGeometry(); dg.setAttribute("position", new Float32BufferAttribute(dp, 3));
  const dust = new Points(dg, new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending, uniforms: { uPx: { value: ctx.px }, uC: { value: acc } },
    vertexShader: `uniform float uPx;void main(){vec4 mv=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*mv;gl_PointSize=1.6*uPx*(10./-mv.z);}`,
    fragmentShader: `uniform vec3 uC;void main(){float d=length(gl_PointCoord-.5);gl_FragColor=vec4(uC,smoothstep(.5,.0,d)*.55);}` }));
  scene.add(dust);
  let boomed = false;
  return {
    logoAt: 2.55, hideLetters: true,
    update(t) {
      mat.uniforms.uT.value = t;
      camera.position.z = lerp(13, 10.2, eout(clamp(t / 3.4)));
      camera.position.x = Math.sin(t * .35) * .5; camera.position.y = Math.cos(t * .3) * .25; camera.lookAt(0, 0, 0);
      dust.rotation.z = t * .02;
      const b = t > 2.45 ? Math.exp(-(t - 2.45) * 3.2) * clamp((t - 2.45) * 14) : 0; mat.uniforms.uBoom.value = b;
      if (!boomed && t > 2.45) { boomed = true; opts.onBeat && opts.onBeat("boom"); }
    }
  };
}

/* ------------------------------------------------------------------------------------------------------------ tunnel */
function tunnelScene(ctx) {
  const { scene, camera, acc, opts } = ctx;
  camera.position.set(0, 0, 0); camera.fov = 62; camera.updateProjectionMatrix();
  const N = ctx.low ? 20 : 30, SP = 2.4, DEPTH = N * SP, rings = [];
  const mkRing = (i) => {
    const col = hsl(acc, i * .014, .0, .06);
    const grp = new Group();
    if (i % 3 === 2) {                                                  // page-shaped frames every third ring
      const w = 3.6, h = 2.5, t = .035, mm = new MeshBasicMaterial({ color: col, transparent: true, opacity: .95, blending: AdditiveBlending, depthWrite: false });
      [[0, h / 2, w, t], [0, -h / 2, w, t], [-w / 2, 0, t, h], [w / 2, 0, t, h]].forEach(([x, y, a, b]) => { const m = new Mesh(new PlaneGeometry(a, b), mm); m.position.set(x, y, 0); grp.add(m); });
    } else {
      const R = 3.1 + (i % 2) * .5;
      grp.add(new Mesh(new TorusGeometry(R, .028, 5, ctx.low ? 40 : 72), new MeshBasicMaterial({ color: col, transparent: true, opacity: .95, blending: AdditiveBlending, depthWrite: false })));
      grp.add(new Mesh(new TorusGeometry(R, .11, 5, ctx.low ? 32 : 56), new MeshBasicMaterial({ color: col, transparent: true, opacity: .14, blending: AdditiveBlending, depthWrite: false })));
    }
    grp.position.z = -i * SP; grp.rotation.z = (i % 3 === 2) ? i * .05 : 0;
    scene.add(grp); return grp;
  };
  for (let i = 0; i < N; i++) rings.push(mkRing(i));
  // star streaks
  const S = ctx.low ? 260 : 600, pos = new Float32Array(S * 2 * 3), ends = new Float32Array(S * 2);
  for (let i = 0; i < S; i++) {
    const a = Math.random() * 6.283, r = rnd(1.2, 11), x = Math.cos(a) * r, y = Math.sin(a) * r * .7, z = -Math.random() * DEPTH;
    for (let k = 0; k < 2; k++) { pos.set([x, y, z], (i * 2 + k) * 3); ends[i * 2 + k] = k; }
  }
  const sg = new BufferGeometry(); sg.setAttribute("position", new Float32BufferAttribute(pos, 3)); sg.setAttribute("aE", new Float32BufferAttribute(ends, 1));
  const sm = new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending, uniforms: { uZ: { value: 0 }, uL: { value: 1 }, uD: { value: DEPTH }, uC: { value: hsl(acc, .06, 0, .3) } },
    vertexShader: `uniform float uZ,uL,uD;attribute float aE;varying float vA;void main(){vec3 p=position;p.z=mod(p.z+uZ,uD)-uD+aE*uL;vec4 mv=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*mv;vA=smoothstep(uD,uD*.55,-p.z)*(.25+.75*(1.-aE));}`,
    fragmentShader: `uniform vec3 uC;varying float vA;void main(){gl_FragColor=vec4(uC,vA);}` });
  const streaks = new LineSegments(sg, sm); scene.add(streaks);
  let z = 0, last = 0, flashed = false;
  return {
    logoAt: 2.7, hideLetters: false,
    update(t) {
      const dt = Math.min(.05, t - last); last = t;
      const speed = lerp(5, 62, sstep(.2, 2.0, t)) * (t > 2.35 ? lerp(1, .06, sstep(2.35, 3.2, t)) : 1);
      z += speed * dt;
      rings.forEach((g, i) => { g.position.z = -i * SP + (z % DEPTH); if (g.position.z > 1.5) g.position.z -= DEPTH; if (g.position.z < -DEPTH + 1.5) g.position.z += DEPTH; });
      // fade rings that are very close
      rings.forEach((g) => { const a = clamp((-g.position.z - .6) / 3) * clamp((DEPTH + g.position.z) / 12); g.children.forEach((m, k) => { m.material.opacity = (m.geometry.type === "TorusGeometry" && m.geometry.parameters.tube > .05 ? .14 : .95) * a; }); });
      sm.uniforms.uZ.value = z; sm.uniforms.uL.value = 1 + speed * .09;
      camera.fov = 62 + sstep(.4, 2, t) * 22 - sstep(2.5, 3.4, t) * 20; camera.updateProjectionMatrix();
      camera.rotation.z = Math.sin(t * 1.1) * .12 * (1 - sstep(2.6, 3.4, t)) + t * .02;
      camera.position.x = Math.sin(t * 2.1) * .25 * (1 - sstep(2.5, 3.2, t)); camera.position.y = Math.cos(t * 1.7) * .2 * (1 - sstep(2.5, 3.2, t));
      if (!flashed && t > 2.7) { flashed = true; opts.onBeat && opts.onBeat("boom"); }
    }
  };
}

/* ------------------------------------------------------------------------------------------------------------ aurora + glass pages */
function pageTexture(variant, acc) {
  const c = document.createElement("canvas"); c.width = 360; c.height = 500; const g = c.getContext("2d");
  const css = "#" + acc.getHexString();
  const r = 26; g.beginPath(); g.moveTo(r, 0); g.lineTo(360 - r, 0); g.quadraticCurveTo(360, 0, 360, r); g.lineTo(360, 500 - r); g.quadraticCurveTo(360, 500, 360 - r, 500); g.lineTo(r, 500); g.quadraticCurveTo(0, 500, 0, 500 - r); g.lineTo(0, r); g.quadraticCurveTo(0, 0, r, 0); g.closePath();
  const gr = g.createLinearGradient(0, 0, 360, 500); gr.addColorStop(0, "rgba(255,255,255,.26)"); gr.addColorStop(1, "rgba(255,255,255,.07)");
  g.fillStyle = gr; g.fill(); g.lineWidth = 3; g.strokeStyle = "rgba(255,255,255,.65)"; g.stroke();
  g.fillStyle = "rgba(255,255,255,.92)"; g.fillRect(28, 30, 304, 34);                       // masthead
  g.fillStyle = "rgba(255,255,255,.7)"; g.fillRect(28, 78, 210, 13);
  const imgY = 104; g.fillStyle = css; g.globalAlpha = .55; g.fillRect(28, imgY, 150 + (variant % 2) * 40, 118); g.globalAlpha = 1;
  g.strokeStyle = "rgba(255,255,255,.7)"; g.lineWidth = 2; g.strokeRect(28, imgY, 150 + (variant % 2) * 40, 118);
  g.fillStyle = "rgba(255,255,255,.55)";
  for (let col = 0; col < 2; col++) for (let l = 0; l < 14; l++) { const x = 28 + col * 156; if (l < 7 && col === (variant % 2 ? 1 : 0) && false) continue; g.fillRect(x, 240 + l * 17, 148 - ((l * 37 + variant * 13) % 5) * 12, 6); }
  const t = new CanvasTexture(c); t.anisotropy = 4; return t;
}
function auroraScene(ctx) {
  const { scene, camera, acc, opts } = ctx;
  camera.position.set(0, 0, 8); camera.fov = 50; camera.updateProjectionMatrix();
  const bg = new Mesh(new PlaneGeometry(2, 2), new ShaderMaterial({
    depthTest: false, depthWrite: false,
    uniforms: { uT: { value: 0 }, uRes: { value: new Vector2(1, 1) }, uBg: { value: new Color(opts.bg) }, uC1: { value: acc }, uC2: { value: hsl(acc, .13, .0, .0) }, uC3: { value: hsl(acc, -.09, .0, .05) }, uK: { value: 1 } },
    vertexShader: `varying vec2 vUv;void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`,
    fragmentShader: `uniform float uT,uK;uniform vec2 uRes;uniform vec3 uBg,uC1,uC2,uC3;varying vec2 vUv;
      float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
      float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}
      float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p=p*2.03+vec2(3.1,1.7);a*=.5;}return v;}
      void main(){vec2 uv=vUv;vec2 p=vec2(uv.x*uRes.x/uRes.y*1.6,uv.y);
        float w=fbm(p*vec2(1.1,.6)+vec2(uT*.07,0.));
        float c1=.52+.22*sin(p.x*1.4+uT*.45+w*3.)+.05*sin(p.x*4.+uT);
        float band=smoothstep(.0,.55,1.-abs(uv.y-c1)*2.4);
        float f=fbm(vec2(p.x*2.2+uT*.12,uv.y*3.-uT*.08)+w*2.);
        vec3 col=mix(uC1,uC2,smoothstep(.25,.8,f))*band*(.45+f*1.1);
        float c2=.34+.18*sin(p.x*1.1-uT*.35+w*2.);float band2=smoothstep(.0,.5,1.-abs(uv.y-c2)*2.8);
        col+=uC3*band2*fbm(p*2.+vec2(-uT*.1,uT*.05))*.9;
        col+=uC1*pow(band,4.)*.25;
        float vg=smoothstep(1.25,.25,length(uv-.5)*1.5);
        gl_FragColor=vec4(uBg+min(col*vg*uK,vec3(.62)),1.);}`
  }));
  bg.frustumCulled = false; bg.renderOrder = -10; scene.add(bg);
  const pages = [], NP = ctx.low ? 6 : 9, tex = [0, 1, 2].map((v) => pageTexture(v, acc));
  for (let i = 0; i < NP; i++) {
    const m = new Mesh(new PlaneGeometry(2.1, 2.9), new MeshBasicMaterial({ map: tex[i % 3], transparent: true, side: DoubleSide, depthWrite: false, opacity: 0 }));
    scene.add(m); pages.push({ m, d: .15 + i * .15 });
  }
  const dots = (() => { const M = ctx.low ? 120 : 260, p = new Float32Array(M * 3); for (let i = 0; i < M; i++) { p[i * 3] = rnd(-12, 12); p[i * 3 + 1] = rnd(-7, 7); p[i * 3 + 2] = rnd(-8, 3); }
    const g = new BufferGeometry(); g.setAttribute("position", new Float32BufferAttribute(p, 3));
    return new Points(g, new ShaderMaterial({ transparent: true, depthWrite: false, blending: AdditiveBlending, uniforms: { uPx: { value: ctx.px } },
      vertexShader: `uniform float uPx;void main(){vec4 mv=modelViewMatrix*vec4(position,1.);gl_Position=projectionMatrix*mv;gl_PointSize=2.2*uPx*(8./-mv.z);}`,
      fragmentShader: `void main(){float d=length(gl_PointCoord-.5);gl_FragColor=vec4(1.,1.,1.,smoothstep(.5,.0,d)*.4);}` })); })();
  scene.add(dots);
  let boomed = false;
  return {
    logoAt: 2.75, hideLetters: false,
    resize(w, h) { bg.material.uniforms.uRes.value.set(w, h); },
    update(t) {
      bg.material.uniforms.uT.value = t + 3;
      bg.material.uniforms.uK.value = lerp(.3, .62, sstep(0, 1.6, t)) + (t > 2.7 ? Math.exp(-(t - 2.7) * 3) * .22 : 0);
      pages.forEach((P, i) => {
        const p = clamp((t - P.d) / 1.05), e = eio(p);
        const conv = sstep(2.1, 2.95, t);                                   // everything is pulled into the centre as the logo appears
        const th = i / pages.length * 6.283 * .75 + t * .22 - 1.2, R = lerp(4.4, 3.0, e) * (1 - conv * .96);
        P.m.position.set(Math.cos(th) * R, Math.sin(i * 1.7 + t * .5) * .55 + (i - pages.length / 2) * .16 * (1 - conv), Math.sin(th) * R * .55 - 1.2 - (1 - e) * 4);
        P.m.rotation.set(Math.sin(t * .6 + i) * .15, -th * .55 + lerp(Math.PI * 1.05, 0, e) + Math.PI * .5 * .0, Math.sin(t * .5 + i * 2) * .12);
        const s = lerp(.6, 1, e) * (1 - conv * .8); P.m.scale.set(s, s, s);
        P.m.material.opacity = clamp(p * 1.6) * (1 - sstep(2.5, 3.0, t)) * .95;
      });
      camera.position.x = Math.sin(t * .3) * .8; camera.position.y = Math.sin(t * .22) * .3; camera.lookAt(0, 0, -1);
      if (!boomed && t > 2.7) { boomed = true; opts.onBeat && opts.onBeat("boom"); }
    }
  };
}

/* ------------------------------------------------------------------------------------------------------------ runner */
export function create(canvas, style, opts) {
  opts = opts || {};
  const renderer = new WebGLRenderer({ canvas, antialias: false, alpha: false, powerPreference: "high-performance" });
  const cap = opts.maxDpr || 1.5;
  let px = Math.min(window.devicePixelRatio || 1, cap), low = !!opts.low;
  renderer.setPixelRatio(px); renderer.setClearColor(new Color(opts.bg || "#0b0c13"), 1);
  const scene = new Scene(), camera = new PerspectiveCamera(50, 1, .1, 200), acc = new Color(opts.accent || "#5b8cff");
  const ctx = { scene, camera, acc, opts, px, low };
  const S = (style === "tunnel" ? tunnelScene : style === "aurora" ? auroraScene : particlesScene)(ctx);
  let raf = 0, t0 = 0, slow = 0, last = 0, idle = false, logoDone = false, W = 0, H = 0, dead = false;
  function size() {
    const r = canvas.getBoundingClientRect(); W = Math.max(2, Math.round(r.width)); H = Math.max(2, Math.round(r.height));
    renderer.setSize(W, H, false); camera.aspect = W / H;
    // keep the framing for narrow windows: widen the field so the content never gets cut off
    if (camera.aspect < 1.4 && style !== "aurora") camera.fov = Math.min(100, camera.fov * (1.4 / camera.aspect) * .9);
    camera.updateProjectionMatrix(); S.resize && S.resize(W, H);
  }
  size(); window.addEventListener("resize", size);
  function frame(now) {
    if (dead) return;
    raf = requestAnimationFrame(frame);
    if (!t0) { t0 = now; last = now; }
    const dt = now - last;
    if (idle && dt < 33) return;                                           // the app is still loading: keep the glow, spend less
    last = now;
    if (dt > 40) { if (++slow > 8 && px > 1) { px = 1; renderer.setPixelRatio(px); size(); } } else if (slow > 0) slow -= .3;
    const t = (now - t0) / 1000;
    S.update(t);
    if (!logoDone && t >= S.logoAt) { logoDone = true; opts.onLogo && opts.onLogo(); }
    renderer.render(scene, camera);
  }
  raf = requestAnimationFrame(frame);
  return {
    hideLetters: S.hideLetters, logoAt: S.logoAt,
    idle() { idle = true; },
    t() { return t0 ? (performance.now() - t0) / 1000 : 0; },
    dispose() { dead = true; cancelAnimationFrame(raf); window.removeEventListener("resize", size); try { renderer.dispose(); renderer.forceContextLoss(); } catch (e) { } }
  };
}
