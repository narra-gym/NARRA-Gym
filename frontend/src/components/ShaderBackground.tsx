import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';

interface ShaderBackgroundProps {
  className?: string;
}

const vertexShader = `
varying vec2 vUv;
void main() { gl_Position = vec4(position, 1.0);
             vUv = uv;
            }
`;

const fragmentShader = `
precision highp float;

uniform vec2 u_resolution;
uniform float u_time;
varying vec2 vUv;
 
const float PI = 3.1415926535897932384626433832795;
const float TAU = PI * 2.;
 

void coswarp(inout vec3 trip, float warpsScale ){

  trip.xyz += warpsScale * .1 * cos(3. * trip.yzx + (u_time * .25));
  trip.xyz += warpsScale * .05 * cos(11. * trip.yzx + (u_time * .25));
  trip.xyz += warpsScale * .025 * cos(17. * trip.yzx + (u_time * .25));
  
}


  
void main() {
  vec2 uv = (gl_FragCoord.xy - u_resolution * .5) / u_resolution.yy + 0.5;
  
  float t = (u_time *.2) + length(fract((uv-.5) *10.));
  
   float t2 = (u_time *.1) + length(fract((uv-.5) *20.));
 
 
 
  vec2 uv2 = uv;
  vec3 w = vec3(uv.x, uv.y, 1.);
  coswarp(w, 3.);
  uv.x += w.r;
  uv.y += w.g;
 
  vec3 base = vec3(0., .5, uv2.x);
  base.r = sin(u_time *.2) + sin(length(uv-.5) * 10.);
  base.g = sin(u_time *.3) + sin(length(uv-.5) * 20.);
  coswarp(base, 3.);
  
  float shade = smoothstep(base.r, sin(t2), sin(t));
  
  // Warm white/beige palette
  vec3 warmA = vec3(1.0, 0.98, 0.94);
  vec3 warmB = vec3(0.96, 0.90, 0.80);
  vec3 warm = mix(warmB, warmA, shade);
  
  // Subtle moving glow to keep motion visible in a light palette
  float glow = 0.06 * sin(u_time * 1.3 + uv.x * 6.0 + uv.y * 4.0);
  warm += glow;
  warm = clamp(warm, 0.0, 1.0);
  
  gl_FragColor = vec4(warm, 1.0);
}
`;

const ShaderBackground: React.FC<ShaderBackgroundProps> = ({ className }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.Camera | null>(null);
  // uniforms kept in closure for type safety with ShaderMaterial
  const clockRef = useRef<THREE.Clock | null>(null);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    clockRef.current = new THREE.Clock();
    cameraRef.current = new THREE.Camera();
    cameraRef.current.position.z = 1;

    sceneRef.current = new THREE.Scene();
    const geometry = new THREE.PlaneGeometry(2, 2);

    const uniforms: Record<string, THREE.IUniform> = {
      u_time: { value: 1.0 },
      u_resolution: { value: new THREE.Vector2() },
    };

    const material = new THREE.ShaderMaterial({
      uniforms,
      vertexShader,
      fragmentShader,
    });

    const mesh = new THREE.Mesh(geometry, material);
    sceneRef.current.add(mesh);

    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    rendererRef.current = renderer;

    container.appendChild(renderer.domElement);

    const onResize = () => {
      if (!rendererRef.current) return;
      rendererRef.current.setSize(window.innerWidth, window.innerHeight);
      uniforms.u_resolution.value.x = rendererRef.current.domElement.width;
      uniforms.u_resolution.value.y = rendererRef.current.domElement.height;
    };

    onResize();
    window.addEventListener('resize', onResize);

    const renderFrame = () => {
      if (!rendererRef.current || !sceneRef.current || !cameraRef.current || !clockRef.current) return;
      uniforms.u_time.value = clockRef.current.getElapsedTime();
      rendererRef.current.render(sceneRef.current, cameraRef.current);
      frameRef.current = requestAnimationFrame(renderFrame);
    };

    renderFrame();

    return () => {
      window.removeEventListener('resize', onResize);
      if (frameRef.current) cancelAnimationFrame(frameRef.current);
      if (rendererRef.current) {
        rendererRef.current.dispose();
        const canvas = rendererRef.current.domElement;
        if (canvas && canvas.parentNode) canvas.parentNode.removeChild(canvas);
      }
    };
  }, []);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ position: 'absolute', inset: 0, zIndex: 0 }}
      aria-hidden
    />
  );
};

export default ShaderBackground;


