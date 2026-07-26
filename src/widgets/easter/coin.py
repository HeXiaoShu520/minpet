# coding:utf-8
import random
import time

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QPushButton

import config
from widgets.easter.base import EasterGamePopup


class CoinPopup(EasterGamePopup):
    title = '抛硬币'

    def __init__(self, x, y, parent=None):
        self.result = random.choice(['正面', '反面'])
        super().__init__(x, y, parent)
        self.setFixedSize(280, 408)
        self.move_to_anchor(x, y)

        self.web = QWebEngineView(self)
        self.web.setGeometry(20, 52, 240, 252)
        self.web.setContextMenuPolicy(Qt.NoContextMenu)
        self.web.setStyleSheet('background: #fff7fa; border: none;')
        self.web.page().setBackgroundColor(QColor(255, 247, 250))
        self.web.setHtml(self._html(self.result), self._base_url())
        self.web.show()
        self.web.raise_()

        self.button = QPushButton('重新抛掷', self)
        self.button.setGeometry(86, 334, 108, 32)
        self.button.setCursor(Qt.PointingHandCursor)
        self.button.setStyleSheet('QPushButton{border:none;border-radius:15px;background:#bd5f86;color:white;font-weight:700;} QPushButton:hover{background:#a84f75;}')
        self.button.clicked.connect(self.toss)
        self.button.show()
        self._play_once('coin_start', 'coin')

    def toss(self):
        self.result = random.choice(['正面', '反面'])
        self.started_at = time.monotonic()
        self.played_sounds.discard('coin_land')
        self.played_sounds.discard('coin_start')
        self.web.setHtml(self._html(self.result), self._base_url())
        self._play_once('coin_start', 'coin')
        self.update()

    def _base_url(self):
        return QUrl.fromLocalFile(str(config.RES_DIR / 'items' / 'easter' / '3d' / 'dice.html'))

    def _html(self, result):
        three_path = (config.RES_DIR / 'items' / 'easter' / '3d' / 'three.min.js').as_posix()
        front_path = (config.RES_DIR / 'items' / 'easter' / 'coin_front.png').as_posix()
        back_path = (config.RES_DIR / 'items' / 'easter' / 'coin_back.png').as_posix()
        final_x = 0 if result == '正面' else 180
        final_y = random.randint(0, 359)
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>
html,body{{margin:0;width:100%;height:100%;overflow:hidden;background:#fff7fa;}}
#stage{{width:240px;height:252px;}}
</style></head><body><div id='stage'></div>
<script src='file:///{three_path}'></script><script>
const W=240,H=252,OA=W/H,OH=5.8;
const scene=new THREE.Scene();
const camera=new THREE.OrthographicCamera(-OH*OA/2,OH*OA/2,OH/2,-OH/2,0.1,100);
camera.position.set(1.5,3.8,5.5); camera.lookAt(0,0.25,0);
const renderer=new THREE.WebGLRenderer({{alpha:true,antialias:true}});
renderer.setSize(W,H); renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));
document.getElementById('stage').appendChild(renderer.domElement);
scene.add(new THREE.AmbientLight(0xffffff,2.6));
const dL=new THREE.DirectionalLight(0xffffff,2.2); dL.position.set(-1.5,5,4); scene.add(dL);
const fL=new THREE.DirectionalLight(0xfff0f8,0.8); fL.position.set(4,1,-2); scene.add(fL);
const pL=new THREE.PointLight(0xffb8e0,0.0,8); pL.position.set(0,1,2); scene.add(pL);
const shadowMesh=new THREE.Mesh(
  new THREE.CircleGeometry(1.5,64),
  new THREE.MeshBasicMaterial({{color:0x6b3a55,transparent:true,opacity:0.0,depthWrite:false}})
);
shadowMesh.rotation.x=-Math.PI/2; shadowMesh.position.set(0,-0.36,0); scene.add(shadowMesh);
function makeFaceTex(isFront){{
  const loader=new THREE.TextureLoader();
  const url=isFront?'file:///{front_path}':'file:///{back_path}';
  const t=loader.load(url,()=>{{renderer.render(scene,camera);}});
  t.colorSpace=THREE.SRGBColorSpace;
  t.anisotropy=renderer.capabilities.getMaxAnisotropy();
  return t;
}}
function makeEdgeTex(){{
  const c=document.createElement('canvas'); c.width=256; c.height=32;
  const g=c.getContext('2d');
  const eg=g.createLinearGradient(0,0,0,32);
  eg.addColorStop(0,'#f0c8b0'); eg.addColorStop(0.25,'#d4907a'); eg.addColorStop(0.5,'#c07860'); eg.addColorStop(0.75,'#d4907a'); eg.addColorStop(1,'#f0c8b0');
  g.fillStyle=eg; g.fillRect(0,0,256,32);
  g.strokeStyle='rgba(255,220,200,0.40)'; g.lineWidth=1;
  for(let x=0;x<256;x+=4){{ g.beginPath(); g.moveTo(x,0); g.lineTo(x,32); g.stroke(); }}
  const t=new THREE.CanvasTexture(c); t.colorSpace=THREE.SRGBColorSpace; return t;
}}
const coinGeo=new THREE.CylinderGeometry(1.32,1.32,0.26,96);
const coinMats=[
  new THREE.MeshStandardMaterial({{map:makeEdgeTex(),roughness:0.15,metalness:0.75}}),
  new THREE.MeshStandardMaterial({{map:makeFaceTex(true),roughness:0.10,metalness:0.0}}),
  new THREE.MeshStandardMaterial({{map:makeFaceTex(false),roughness:0.10,metalness:0.0}}),
];
const coin=new THREE.Mesh(coinGeo,coinMats);
scene.add(coin);
const finalRad={{x:{final_x}*Math.PI/180,y:{final_y}*Math.PI/180,z:0}};
const GROUND=-0.35,THROW_H=3.8;
const DUR_FLY=900,DUR_B1=300,DUR_B2=200,DUR_SETTLE=180;
const TOTAL=DUR_FLY+DUR_B1+DUR_B2+DUR_SETTLE;
const spinX0=(Math.random()*3+2.5)*Math.PI*2;
const spinY0=(Math.random()*0.8+0.5)*Math.PI*2;
const T0=performance.now();
function tick(now){{
  const el=now-T0;
  let worldY,rx,ry2,rz=0,sOp,sS,glowI;
  if(el<DUR_FLY){{
    const p=el/DUR_FLY,fp=p*p,h=THROW_H*(1-fp);
    worldY=GROUND+h;
    rx=finalRad.x+spinX0*(1-p); ry2=finalRad.y+spinY0*(1-p);
    sOp=0.04+(1-h/THROW_H)*0.22; sS=0.3+(1-h/THROW_H)*0.75;
    glowI=0.0;
  }} else if(el<DUR_FLY+DUR_B1){{
    const p=(el-DUR_FLY)/DUR_B1,f=Math.pow(1-p,2);
    worldY=GROUND+Math.sin(p*Math.PI)*0.45;
    rx=finalRad.x+spinX0*f*0.08; ry2=finalRad.y+spinY0*f*0.06;
    sOp=0.22-Math.sin(p*Math.PI)*0.06; sS=1.0-Math.sin(p*Math.PI)*0.16;
    glowI=p*1.2;
  }} else if(el<DUR_FLY+DUR_B1+DUR_B2){{
    const p=(el-DUR_FLY-DUR_B1)/DUR_B2;
    worldY=GROUND+Math.sin(p*Math.PI)*0.14;
    rx=finalRad.x; ry2=finalRad.y;
    sOp=0.22; sS=1.0-Math.sin(p*Math.PI)*0.05;
    glowI=1.2+p*0.6;
  }} else {{
    const p=Math.min(1,(el-DUR_FLY-DUR_B1-DUR_B2)/DUR_SETTLE);
    const j=Math.sin(p*Math.PI*4)*(1-p)*0.012;
    worldY=GROUND; rx=finalRad.x+j; ry2=finalRad.y; rz=j*0.3;
    sOp=0.24; sS=1.0;
    glowI=1.4+Math.sin((el-TOTAL)*0.004)*0.4;
  }}
  coin.position.y=worldY; coin.rotation.x=rx; coin.rotation.y=ry2; coin.rotation.z=rz;
  pL.intensity=glowI; pL.position.set(0,worldY+0.5,1.8);
  shadowMesh.material.opacity=Math.min(sOp,0.30);
  const s=Math.max(0.3,sS); shadowMesh.scale.set(s,s,s);
  renderer.render(scene,camera);
  if(el<TOTAL) requestAnimationFrame(tick);
}}
requestAnimationFrame(tick);
</script></body></html>"""

    def paintEvent(self, event):
        painter = QPainter(self)
        self._draw_card(painter, QColor(255, 247, 250, 248), QColor(238, 180, 202, 230))
        if self._elapsed() > 1.6:
            self._play_once('coin_land', 'drop')
            painter.setFont(QFont('Microsoft YaHei UI', 12, QFont.Bold))
            painter.setPen(QColor(116, 56, 82))
            painter.drawText(0, 304, self.width(), 24, Qt.AlignCenter, f'结果：{self.result}')
