"""ARC-AGI-3 local worker. Only public frames/actions cross the model boundary."""
import contextlib
import json
import logging
from pathlib import Path
import re
import select
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
COLORS=['#FFFFFF','#CCCCCC','#999999','#666666','#333333','#000000','#E53AA3',
        '#FF7BCC','#F93C31','#1E93FF','#88D8F1','#FFDC00','#FF851B','#921231','#4FCC30','#A356D6']

def encode_frames(frames):
    encoded=[]
    for frame in frames:
        rows=[]
        for y,row in enumerate(frame):
            text=''.join(format(int(v),'X') for v in row)
            if rows and rows[-1][2]==text: rows[-1][1]=y
            else: rows.append([y,y,text])
        encoded.append({'width':len(frame[0]) if len(frame) else 0,'height':len(frame),'rows':rows})
    return encoded

class ArcSession:
    def __init__(self,game_id,seed=0):
        if not re.fullmatch(r'[a-z0-9]+-[a-z0-9]+',game_id): raise ValueError('Use a versioned ARC game ID')
        python=ROOT/'runs/runtime/arc-venv/bin/python'
        if not python.exists():raise ValueError('ARC runtime not installed')
        self.lock=threading.Lock()
        self.process=subprocess.Popen([str(python),str(Path(__file__).resolve()),game_id,str(seed)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1,
            cwd=str(ROOT/'runs/runtime'),env={'PATH':'/usr/bin:/bin','MPLCONFIGDIR':str(ROOT/'runs/runtime/mpl')})
        try:self.observation=self._read()
        except BaseException:self.close();raise

    def _read(self):
        if not select.select([self.process.stdout],[],[],30)[0]:
            raise ValueError('ARC environment response timed out')
        line=self.process.stdout.readline()
        if not line:raise ValueError('ARC environment worker stopped')
        message=json.loads(line)
        if 'error' in message:raise ValueError(message['error'])
        return message

    def step(self,action,x=None,y=None):
        if action not in self.observation['available_actions'] and action!='RESET':
            raise ValueError('Action not available in current observation')
        if self.observation['state']=='WIN':raise ValueError('Environment already won')
        if self.observation['state']=='GAME_OVER' and action!='RESET':raise ValueError('RESET required after GAME_OVER')
        if action=='ACTION6' and any(isinstance(v,bool) or not isinstance(v,int) or not 0<=v<64 for v in (x,y)):
            raise ValueError('ACTION6 requires x,y in 0..63')
        if action!='ACTION6' and (x is not None or y is not None):raise ValueError('Coordinates only apply to ACTION6')
        with self.lock:
            self.process.stdin.write(json.dumps({'action':action,'x':x,'y':y})+'\n');self.process.stdin.flush()
            self.observation=self._read()
            return self.observation

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        for stream in (self.process.stdin,self.process.stdout):
            if stream:stream.close()

def worker(game_id,seed):
    logging.disable(logging.CRITICAL)
    import arc_agi
    from arcengine import GameAction
    # Game code is held by this trusted worker, never mounted into Python/WASI.
    with contextlib.redirect_stdout(sys.stderr):
        arc=arc_agi.Arcade(operation_mode=arc_agi.OperationMode.OFFLINE,environments_dir=str(ROOT/'runs/runtime/arc-games'))
        env=arc.make(game_id,seed=seed)
        if env is None:raise ValueError('Local game unavailable')
        obs=env.reset()
    def public(obs):
        return dict(game_id=obs.game_id,state=obs.state.value,levels_completed=obs.levels_completed,
                    win_levels=obs.win_levels,available_actions=['ACTION'+str(v) for v in obs.available_actions],
                    frames=encode_frames(obs.frame))
    print(json.dumps(public(obs)),flush=True)
    for line in sys.stdin:
        try:
            req=json.loads(line);action=GameAction[req['action']]
            data={'x':req['x'],'y':req['y']} if action.is_complex() else {}
            with contextlib.redirect_stdout(sys.stderr):
                obs=env.reset() if action==GameAction.RESET else env.step(action,data=data)
            print(json.dumps(public(obs)),flush=True)
        except Exception:
            print(json.dumps({'error':'ARC action failed'}),flush=True)

if __name__=='__main__':worker(sys.argv[1],int(sys.argv[2]))
