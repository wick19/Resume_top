/* eslint-disable react/no-unknown-property */
import React, { forwardRef, useMemo, useRef, useLayoutEffect, useEffect } from 'react';
import { Canvas, useFrame, useThree, type RootState } from '@react-three/fiber';
import { Color, Mesh, ShaderMaterial, Vector2 } from 'three';
import { type IUniform } from 'three';

type NormalizedRGB = [number, number, number];

const hexToNormalizedRGB = (hex: string): NormalizedRGB => {
  const clean = hex.replace('#', '');
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;
  return [r, g, b];
};

interface UniformValue<T = number | Color | Vector2> {
  value: T;
}

interface SilkUniforms {
  uSpeed: UniformValue<number>;
  uScale: UniformValue<number>;
  uNoiseIntensity: UniformValue<number>;
  uColor: UniformValue<Color>;
  uRotation: UniformValue<number>;
  uLightMode: UniformValue<number>;
  uRibbon: UniformValue<number>;
  uHighlight: UniformValue<Color>;
  uLift: UniformValue<number>;
  uTime: UniformValue<number>;
  uPointer: UniformValue<Vector2>;
  [uniform: string]: IUniform;
}

const vertexShader = `
varying vec2 vUv;
varying vec3 vPosition;

void main() {
  vPosition = position;
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const fragmentShader = `
varying vec2 vUv;
varying vec3 vPosition;

uniform float uTime;
uniform vec3  uColor;
uniform float uSpeed;
uniform float uScale;
uniform float uRotation;
uniform float uNoiseIntensity;
uniform float uLightMode;
uniform float uRibbon;
uniform vec3 uHighlight;
uniform float uLift;
uniform vec2 uPointer;

const float e = 2.71828182845904523536;

float noise(vec2 texCoord) {
  float G = e;
  vec2  r = (G * sin(G * texCoord));
  return fract(r.x * r.y * (1.0 + texCoord.x));
}

vec2 rotateUvs(vec2 uv, float angle) {
  float c = cos(angle);
  float s = sin(angle);
  mat2  rot = mat2(c, -s, s, c);
  return rot * uv;
}

void main() {
  float rnd        = noise(gl_FragCoord.xy);
  vec2  uv         = rotateUvs(vUv * uScale, uRotation);
  vec2  tex        = uv * uScale;
  float sway = uRibbon > 0.5 ? 0.32 : 0.14;
  tex += (uPointer - 0.5) * sway;
  float tOffset    = uSpeed * uTime;

  tex.y += 0.03 * sin(8.0 * tex.x - tOffset);
  if (uRibbon > 0.5) {
    tex.x += 0.06 * sin(tOffset * 0.42);
    tex.y += 0.035 * cos(tOffset * 0.28 + tex.x);
  }

  float pattern = 0.6 +
                  0.4 * sin(5.0 * (tex.x + tex.y +
                                   cos(3.0 * tex.x + 5.0 * tex.y) +
                                   0.02 * tOffset) +
                           sin(20.0 * (tex.x + tex.y - 0.1 * tOffset)));

  float grain = rnd / 15.0 * uNoiseIntensity;
  vec3 result = uColor * pattern - vec3(grain);
if (uLightMode > 0.5) {
  float fold = smoothstep(0.28, 0.9, pattern);
  float specular = smoothstep(0.72, 0.98, pattern);
  vec3 shadowColor = uRibbon > 0.5
    ? mix(uColor, uHighlight, uLift > 0.5 ? 0.55 : 0.0) * (uLift > 0.5 ? 0.92 : 0.42)
    : uColor * 0.72;
  vec3 bodyColor = uRibbon > 0.5
    ? mix(uColor, uHighlight, 0.32)
    : min(uColor * 1.18, vec3(1.0));
  vec3 lightBase = mix(shadowColor, bodyColor, fold);
  vec3 specTarget = uRibbon > 0.5 ? uHighlight : vec3(1.0);
  float specAmt = uRibbon > 0.5 ? 0.58 : 0.92;
  lightBase = mix(lightBase, specTarget, specular * specAmt);
  float fineNoise = noise(gl_FragCoord.xy * 0.63 + vec2(17.0, 41.0));
  float grainSignal = (rnd + fineNoise - 1.0);
  float grainStrength = clamp(uNoiseIntensity * 0.038, 0.0, 0.16);
  result = lightBase + grainSignal * grainStrength;
}
  gl_FragColor = vec4(clamp(result, 0.0, 1.0), 1.0);
}
`;

interface SilkPlaneProps {
  uniforms: SilkUniforms;
}

const SilkPlane = forwardRef<Mesh, SilkPlaneProps>(function SilkPlane({ uniforms }, ref) {
  const { viewport } = useThree();
  const pointer = useRef({ x: 0.5, y: 0.5 });

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      pointer.current.x = event.clientX / window.innerWidth;
      pointer.current.y = 1 - event.clientY / window.innerHeight;
    };
    window.addEventListener('pointermove', onMove);
    return () => window.removeEventListener('pointermove', onMove);
  }, []);

  useLayoutEffect(() => {
    const mesh = ref as React.MutableRefObject<Mesh | null>;
    if (mesh.current) {
      mesh.current.scale.set(viewport.width, viewport.height, 1);
    }
  }, [ref, viewport]);

  useFrame((_state: RootState, delta: number) => {
    const mesh = ref as React.MutableRefObject<Mesh | null>;
    if (mesh.current) {
      const material = mesh.current.material as ShaderMaterial & {
        uniforms: SilkUniforms;
      };
      material.uniforms.uTime.value += 0.1 * delta;
      const current = material.uniforms.uPointer.value;
      current.x += (pointer.current.x - current.x) * 0.06;
      current.y += (pointer.current.y - current.y) * 0.06;
    }
  });

  return (
    <mesh ref={ref}>
      <planeGeometry args={[1, 1, 1, 1]} />
      <shaderMaterial uniforms={uniforms} vertexShader={vertexShader} fragmentShader={fragmentShader} />
    </mesh>
  );
});
SilkPlane.displayName = 'SilkPlane';

export interface SilkProps {
  speed?: number;
  scale?: number;
  color?: string;
  noiseIntensity?: number;
  rotation?: number;
  lightMode?: boolean;
  ribbon?: boolean;
  highlight?: string;
  lift?: boolean;
}

const Silk: React.FC<SilkProps> = ({
  speed = 5,
  scale = 1,
  color = '#7B7481',
  noiseIntensity = 1.5,
  rotation = 0,
  lightMode = false,
  ribbon = false,
  highlight = '#00a0f0',
  lift = false
}) => {
  const meshRef = useRef<Mesh>(null);

  const uniforms = useMemo<SilkUniforms>(
    () => ({
      uSpeed: { value: speed },
      uScale: { value: scale },
      uNoiseIntensity: { value: noiseIntensity },
      uColor: { value: new Color(...hexToNormalizedRGB(color)) },
      uRotation: { value: rotation },
      uLightMode: { value: lightMode ? 1 : 0 },
      uRibbon: { value: ribbon ? 1 : 0 },
      uHighlight: { value: new Color(...hexToNormalizedRGB(highlight)) },
      uLift: { value: lift ? 1 : 0 },
      uTime: { value: 0 },
      uPointer: { value: new Vector2(0.5, 0.5) }
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  useEffect(() => {
    uniforms.uSpeed.value = speed;
    uniforms.uScale.value = scale;
    uniforms.uNoiseIntensity.value = noiseIntensity;
    uniforms.uColor.value.setRGB(...hexToNormalizedRGB(color));
    uniforms.uRotation.value = rotation;
    uniforms.uLightMode.value = lightMode ? 1 : 0;
    uniforms.uRibbon.value = ribbon ? 1 : 0;
    uniforms.uHighlight.value.setRGB(...hexToNormalizedRGB(highlight));
    uniforms.uLift.value = lift ? 1 : 0;
  }, [speed, scale, noiseIntensity, color, rotation, lightMode, ribbon, highlight, lift, uniforms]);

  return (
    <Canvas
      dpr={[1, 2]}
      frameloop="always"
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
    >
      <SilkPlane ref={meshRef} uniforms={uniforms} />
    </Canvas>
  );
};

export default Silk;
