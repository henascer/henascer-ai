import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pandas as pd
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import io


# 제미나이 설정 및 모델 선언
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

model = genai.GenerativeModel(
    'nano-banana-pro-preview',
    safety_settings={
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
    }
)

# --- [0. 세션 상태 초기화] ---
if 'styling_done' not in st.session_state:
    st.session_state.styling_done = False
if 'final_image' not in st.session_state:
    st.session_state.final_image = None
if 'synthesis_count' not in st.session_state:
    st.session_state.synthesis_count = 0 
if 'current_prompt' not in st.session_state:
    st.session_state.current_prompt = None
if 'last_files' not in st.session_state:
    st.session_state.last_files = None

# --- [함수: 합성 로직] ---
def run_synthesis(mode, img_a, img_b, idx, remaining):
    try:
        # 1. 생성 설정(Generation Config) 정의
        # 온도를 낮추면 결과가 일관되고 얼굴 왜곡이 줄어듭니다.
        generation_config = {
            "temperature": 0.4,  # 0.0 ~ 2.0 사이 (낮을수록 보수적/안정적)
            "top_p": 0.95,       # 상위 확률 분포 조절
            "top_k": 32,         # 후보군 제한
            "max_output_tokens": 1024,
        }

        # 2. 프롬프트 생성
        prompt = f"""
        [Role]: You are a Master AI Stylist specializing in photo-realistic Virtual Try-on.

        [Input]:
        - Image 1 (The FIRST image): BASE_IMAGE (The customer)
        - Image 2 (The SECOND image): STYLE_IMAGE (The reference look)

        [PRIME DIRECTIVE - CRITICAL]:
        1. TARGET RECOGNITION: Focus ONLY on the human subject's head and body. Strictly ignore all mobile UI elements (status bars, notches, buttons, white/black bars) in both images.
        2. DO NOT CHANGE the person's head angle, facial expression, or eye direction from Image 1. 
        3. Image 1 is the MASTER for the face. Keep the identity, skin tone, and features 100% identical.
        4. Extract ONLY the {mode} style from Image 2 and apply it onto the person in Image 1.
        5. The output must have the EXACT SAME facial alignment and camera angle as Image 1.
        
        [Task]:
        - "Surgically" replace ONLY the {mode} of the person in Image 1 with the style from Image 2.
        - Head Pose Alignment: Ensure the new {mode} is naturally fitted onto the original head position of Image 1.
        - Seamless Blending: The hairline and the area where the skin meets the {mode} must be perfectly blended with realistic shadows.
        - Preservation: Keep the original facial features (eyebrows, eyes, skin texture), background, and clothing of Image 1 untouched.

        [Important Rules]:
        - The result must be a SINGLE integrated photo, NOT a side-by-side comparison.
        - The person's identity and facial proportions must remain 100% recognizable as the person in Image 1.
        - No text, no descriptions, no watermarks. Output ONLY the resulting image.
        """
        st.session_state.current_prompt = prompt

        # 3. 이미지 생성 요청 시 config 반영
        response = model.generate_content(
            [st.session_state.current_prompt, img_a, img_b],
            generation_config=generation_config 
        )
        
        image_data = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break
        
        if image_data:
            # 원본 결과물 코드
            base_image = Image.open(io.BytesIO(image_data)).convert("RGBA")

            # 로고 코드 및 설정
            try : 
                logo = Image.open("logo.png").convert("RGBA")
                target_width = int(base_image.width * 0.15)

                logo_resized = logo.resize((target_width, int(target_width * (logo.height/logo.width))), Image.LANCZOS)
                logo_resized.putalpha(150) # 투명도 (0~255, 150정도면 선명하면서도 자연스러움)

                # 워터마크 레이어 생성
                watermark_layer = Image.new('RGBA', base_image.size, (0,0,0,0))
                padding = 30
                position = (base_image.width - logo_resized.width - padding, 
                            base_image.height - logo_resized.height - padding)

                # 레이어에 로고 부착
                watermark_layer.paste(logo_resized, position, mask=logo_resized)

                # 원본과 워터마크 레이어 병합
                final_combined_image = Image.alpha_composite(base_image, watermark_layer)
                st.session_state.final_image = final_combined_image.convert("RGB") # 세션 저장
            
            except FileNotFoundError:
                st.warning("⚠️ logo.png 파일을 찾을 수 없어 원본 이미지만 표시합니다.")
                st.session_state.final_image = base_image.convert("RGB")
                
        st.session_state.styling_done = True
        return True
    
    except Exception as e:
        st.error(f"합성 엔진 오류: {e}")
        return False

# 1. 페이지 설정
st.set_page_config(page_title="헤나세르 가상 스타일링", layout="centered")

# 깔끔하게 메뉴와 푸터만 숨기기 (헤더 유지하여 키 입력창 보호)
st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>""", unsafe_allow_html=True)

# 2. 인증 설정
try:
    # Google Sheets 인증
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gspread_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    # 시트 열기
    sh = client.open_by_url(st.secrets["gsheets_url"])
    worksheet = sh.get_worksheet(0)
except Exception as e:
    st.error(f"설정 오류: {e}")
    st.stop()

# --- [3. 메인 로직 시작] ---
# 액세스 키를 사이드바가 아닌 화면 최상단에 배치
st.markdown("### 🔑 가상 스타일링 멤버십 인증")
access_key = st.text_input("액세스 키를 입력하세요 (대소문자 구분)", type="password")

if access_key:
    # 실시간 시트 데이터 확인
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    user_row = df[df['Access_Key'].astype(str) == access_key]

    if not user_row.empty:
        idx = user_row.index[0]  # 시트에서의 행 위치
        remaining = int(user_row.iloc[0]['Remaining_Count'])
        
        if remaining > 0:
            st.success(f"✅ 인증 성공! 잔여 횟수: {remaining}회")
            
            # 1. 스타일 선택
            mode = st.selectbox("어떤 스타일을 시뮬레이션할까요?", ["헤어"])
            
            st.markdown("---")

            # 2. 내 정면 사진 (Base) 섹션
            st.markdown("### 👤 <span style='font-size: 24px;'>내 정면 사진</span>", unsafe_allow_html=True)
            base_img_file = st.file_uploader("본인의 정면 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")
            
            st.markdown("---")

            # 3. 합성할 헤어 사진 (Style) 섹션
            st.markdown("### 💇‍♂️ <span style='font-size: 24px;'>합성할 헤어 사진</span>", unsafe_allow_html=True)
            st.info("💡 아래와 같은 '정면' 예시를 준비해주세요. (측면 사진은 불가해요)")
            st.image("example_front.jpg", width=250, caption="[합성이 잘 되는 정면 예시]")
            
            style_img_file = st.file_uploader("원하는 헤어 스타일 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")

            st.markdown("---")

            # [핵심] 사진이 바뀌면 자동으로 결과물 초기화
            current_files = f"{base_img_file.name if base_img_file else ''}_{style_img_file.name if style_img_file else ''}"
            if st.session_state.last_files != current_files:
                st.session_state.styling_done = False
                st.session_state.final_image = None
                st.session_state.synthesis_count = 0
                st.session_state.last_files = current_files

            # 4. 합성 실행 버튼 (결과가 없을 때만 노출)
            if base_img_file and style_img_file and not st.session_state.styling_done:
                if st.button(f"✨ {mode} 합성 시작하기 (1~2분 소요)"):
                    with st.spinner("1~2분 정도 소요됩니다. 페이지를 이탈하거나 새로고침 하지 마세요."):
                        try:
                            img_a = Image.open(base_img_file)
                            img_b = Image.open(style_img_file)

                            if run_synthesis(mode, img_a, img_b, idx, remaining):
                                st.session_state.synthesis_count = 1
                                worksheet.update_cell(idx + 2, 3, remaining - 1)
                                st.rerun()

                            else:
                                st.error("이미지를 생성하지 못했습니다. 다시 시도해 주세요. (횟수 차감 X)")
                        except Exception as e:
                            st.error(f"합성 엔진 오류: {e}")

            # 5. 결과물 섹션
            if st.session_state.styling_done and st.session_state.final_image:
                # (1) 합성 사진
                st.image(st.session_state.final_image, use_column_width=True)

                # (2) 스타일 방향성 주의 문구
                st.markdown(f"""
                <div style='text-align: center; background-color: #f8f9fa; padding: 20px; border-radius: 10px; margin-top: 15px;'>
                    <p style='color: #555555; font-size: 14px; line-height: 1.6;'>
                        본 결과는 스타일 방향성을 보기 위한 <b>AI 시뮬레이션</b>입니다.<br>
                        각도나 조명에 따라 실제와 차이가 발생할 수 있습니다.
                    </p>
                    <p style='color: #333333; font-size: 15px; font-weight: bold; margin-top: 10px;'>
                        🧐 결과가 마음에 들지 않으신가요?<br>
                        <span style='color: #007bff;'>재합성</span>을 시도하거나,<br>
                        <span style='color: #007bff;'>다른 사진</span>으로 다시 테스트 해보세요!
                    </p>
                </div>
                """, unsafe_allow_html=True)

                    
                # (3) 재합성 버튼 (확인창 없이 즉시 실행, 1회만 가능)
                if st.session_state.synthesis_count == 1:
                    st.write("")
                    if st.button("🔄 재합성 시도하기 (무료 1회)"):
                        with st.spinner("1~2분 정도 소요됩니다. 페이지를 이탈하거나 새로고침 하지 마세요."):
                            img_a = Image.open(base_img_file)
                            img_b = Image.open(style_img_file)
                            if run_synthesis(mode, img_a, img_b, idx, remaining):
                                st.session_state.synthesis_count = 2
                                st.rerun()

                # (4) 좋아요 버튼
                st.write("")
                if st.button("👍 이 결과가 마음에 드시나요? (서비스 반영)"):
                    try:
                        current_likes_val = worksheet.cell(idx + 2, 4).value
                        current_likes = int(current_likes_val) if current_likes_val and str(current_likes_val).isdigit() else 0
                        worksheet.update_cell(idx + 2, 4, current_likes + 1)
                        st.toast("피드백 감사합니다! 😊")
                    except: pass

        else:
            st.error("잔여 횟수가 없습니다. 충전이 필요합니다.")
    else:
        st.error("잘못된 키입니다.")
else:
    st.info("계속하려면 인증 키를 입력해주세요.")