import sys
import socket
import argparse
import json
import re
import time
import numpy as np
from PyQt5 import QtCore, QtWidgets
import pyqtgraph.opengl as gl
import pyqtgraph as pg

# UDP Listener implemented as QThread
class UDPListener(QtCore.QThread):
    orientation_received = QtCore.pyqtSignal(float, float, float)
    error = QtCore.pyqtSignal(str)

    def __init__(self, listen_ip="0.0.0.0", listen_port=8888, parent=None):
        super().__init__(parent)
        self.listen_ip = listen_ip
        self.listen_port = int(listen_port)
        self._running = False
        self.sock = None

    def _parse_message(self, s):
        s = s.strip()
        # Try JSON first
        try:
            data = json.loads(s)
            # accept keys like H,P,R or heading,pitch,roll (case-insensitive)
            keys = {k.lower(): v for k, v in data.items()}
            if 'h' in keys or 'heading' in keys:
                h = keys.get('h', keys.get('heading'))
                p = keys.get('p', keys.get('pitch'))
                r = keys.get('r', keys.get('roll'))
                if h is not None and p is not None and r is not None:
                    return float(h), float(p), float(r)
        except Exception:
            pass

        # Key-value style (H:..., P=..., R:...) in any order
        m = re.findall(r'([HhPpRr]|heading|pitch|roll)[:=]\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', s)
        if m:
            d = {}
            for k, v in m:
                kk = k.lower()
                if kk.startswith('h'):
                    d['h'] = float(v)
                elif kk.startswith('p'):
                    d['p'] = float(v)
                elif kk.startswith('r'):
                    d['r'] = float(v)
            if 'h' in d and 'p' in d and 'r' in d:
                return d['h'], d['p'], d['r']

        # fallback: pick first three floats found
        m2 = re.findall(r'(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', s)
        if len(m2) >= 3:
            return float(m2[0]), float(m2[1]), float(m2[2])

        return None

    def run(self):
        self._running = True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.listen_ip, self.listen_port))
            self.sock.settimeout(0.5)
        except Exception as e:
            self.error.emit(f"Socket bind error: {e}")
            return

        print(f"[UDPListener] Listening on {self.listen_ip}:{self.listen_port}")
        while self._running:
            try:
                data, addr = self.sock.recvfrom(4096)
                text = data.decode('utf-8', errors='ignore')
                parsed = self._parse_message(text)
                if parsed:
                    h, p, r = parsed
                    # emit to main thread
                    self.orientation_received.emit(float(h), float(p), float(r))
                else:
                    # you can enable the line below for debugging unparsed packets
                    # print("[UDPListener] Unparsed:", text)
                    pass
            except socket.timeout:
                continue
            except Exception as e:
                # emit error and break
                self.error.emit(f"UDP listener exception: {e}")
                break

        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        print("[UDPListener] Stopped")

    def stop(self):
        self._running = False
        # wait for thread to finish
        self.wait(1000)


# 3D Visualization Widget
class BoatVisualizer(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.view = gl.GLViewWidget()
        self.view.setCameraPosition(distance=4.0)
        self.view.opts['fov'] = 60

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        # unit sphere
        md = gl.MeshData.sphere(rows=30, cols=30, radius=1.0)
        self.sphere = gl.GLMeshItem(meshdata=md, smooth=True, color=(0.7,0.7,0.85,0.18), drawEdges=False)
        self.sphere.setGLOptions('translucent')
        self.view.addItem(self.sphere)


        # boat body axes (forward, right, up)
        self.fwd_line = gl.GLLinePlotItem(pos=np.array([[0,0,0],[1,0,0]]), color=(1,0.5,0,1), width=4, mode='lines')
        self.rgt_line = gl.GLLinePlotItem(pos=np.array([[0,0,0],[0,1,0]]), color=(0,1,0.2,1), width=4, mode='lines')
        self.up_line  = gl.GLLinePlotItem(pos=np.array([[0,0,0],[0,0,1]]), color=(0.2,0.6,1,1), width=4, mode='lines')
        self.view.addItem(self.fwd_line)
        self.view.addItem(self.rgt_line)
        self.view.addItem(self.up_line)

        # tip (scatter) to mark forward vector tip
        self.tip = gl.GLScatterPlotItem(pos=np.array([[1,0,0]]), size=8, pxMode=False)
        self.view.addItem(self.tip)

        # overlay labels (QLabels)
        self.info_label = QtWidgets.QLabel(self)
        self.info_label.setStyleSheet("background: rgba(0,0,0,0.45); color: white; padding: 4px; border-radius:4px;")
        self.info_label.setFixedWidth(260)
        self.info_label.setText("H: ---, P: ---, R: ---")

        self.lbl_x = QtWidgets.QLabel("X (forward)", self)
        self.lbl_x.setStyleSheet("color: orange; background: rgba(0,0,0,0);")
        self.lbl_y = QtWidgets.QLabel("Y (right)", self)
        self.lbl_y.setStyleSheet("color: green; background: rgba(0,0,0,0);")
        self.lbl_z = QtWidgets.QLabel("Z (up)", self)
        self.lbl_z.setStyleSheet("color: cyan; background: rgba(0,0,0,0);")

        self.heading = 0.0
        self.pitch = 0.0
        self.roll = 0.0

        # update label positions after widget shown
        QtCore.QTimer.singleShot(50, self._place_overlays)

    def _place_overlays(self):
        # position overlay labels relative to widget size
        margin = 8
        w = self.width()
        h = self.height()
        self.info_label.move(margin, margin)
        # place axis labels bottom-right-ish (approximate, since 3D -> 2D projection not computed)
        self.lbl_x.move(w - 100, h - 40)
        self.lbl_y.move(w - 100, h - 60)
        self.lbl_z.move(w - 100, h - 80)

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._place_overlays()

    @staticmethod
    def rotation_matrix_from_euler(roll_deg, pitch_deg, heading_deg):
        # Intrinsic rotations: Rx(roll) then Ry(pitch) then Rz(yaw) -> R = Rz * Ry * Rx
        r = np.deg2rad(roll_deg)
        p = np.deg2rad(pitch_deg)
        y = np.deg2rad(heading_deg)

        Rx = np.array([[1, 0, 0],
                       [0, np.cos(r), -np.sin(r)],
                       [0, np.sin(r),  np.cos(r)]])

        Ry = np.array([[ np.cos(p), 0, np.sin(p)],
                       [0, 1, 0],
                       [-np.sin(p), 0, np.cos(p)]])

        Rz = np.array([[np.cos(y), -np.sin(y), 0],
                       [np.sin(y),  np.cos(y), 0],
                       [0, 0, 1]])
        R = Rz @ Ry @ Rx
        return R

    def set_orientation(self, heading, pitch, roll):
        # Store degrees and update visuals
        self.heading = float(heading)
        self.pitch = float(pitch)
        self.roll = float(roll)
        self._update_visuals()

    def _update_visuals(self):
        R = self.rotation_matrix_from_euler(self.roll, self.pitch, self.heading)

        fwd_b = np.array([1.0, 0.0, 0.0])
        rgt_b = np.array([0.0, 1.0, 0.0])
        up_b  = np.array([0.0, 0.0, 1.0])

        fwd_w = R @ fwd_b
        rgt_w = R @ rgt_b
        up_w  = R @ up_b

        # avoid zero-division
        def normed(v):
            n = np.linalg.norm(v)
            if n < 1e-8:
                return np.zeros(3)
            return v / n

        fwd_w = normed(fwd_w)
        rgt_w = normed(rgt_w)
        up_w  = normed(up_w)

        # update lines and tip
        self.fwd_line.setData(pos=np.vstack(([0,0,0], fwd_w)))
        self.rgt_line.setData(pos=np.vstack(([0,0,0], rgt_w)))
        self.up_line.setData(pos=np.vstack(([0,0,0], up_w)))
        self.tip.setData(pos=np.array([fwd_w]), size=8)

        # update numeric label
        self.info_label.setText(f"H: {self.heading:.1f}°   P: {self.pitch:.1f}°   R: {self.roll:.1f}°")



# Main Window
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, listen_ip="0.0.0.0", listen_port=8888):
        super().__init__()
        self.setWindowTitle("Boat Orientation Viewer (UDP)")
        self.resize(900, 650)

        self.vis = BoatVisualizer()
        self.setCentralWidget(self.vis)

        # UDP worker thread
        self.udp = UDPListener(listen_ip=listen_ip, listen_port=listen_port)
        self.udp.orientation_received.connect(self.on_orientation)
        self.udp.error.connect(self.on_udp_error)
        self.udp.start()

    @QtCore.pyqtSlot(float, float, float)
    def on_orientation(self, h, p, r):
        # called in Qt main thread
        self.vis.set_orientation(h, p, r)

    @QtCore.pyqtSlot(str)
    def on_udp_error(self, msg):
        print("[UDP Error]", msg)
        QtWidgets.QMessageBox.critical(self, "UDP Error", msg)

    def closeEvent(self, ev):
        # stop UDP thread cleanly
        if hasattr(self, "udp") and self.udp is not None:
            self.udp.stop()
        time.sleep(0.02)
        super().closeEvent(ev)



# CLI + Run
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ip", default="0.0.0.0", help="IP/interface to bind")
    parser.add_argument("--port", type=int, default=8888, help="UDP port to listen on")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(listen_ip=args.ip, listen_port=args.port)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
