import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image, ImageOps, ImageDraw, ImageFont
import pandas as pd
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import io

# 모델 선언 부분
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
        # 프롬프트 생성
        prompt = f"""
        URGENT: Strict head pose alignment. The nose and eyes in the output MUST be in the exact same pixel coordinates as Image A.
        [Role]: You are a Master AI Stylist specializing in photo-realistic Virtual Try-on.
        [Input]:
        - Image 1 (The FIRST image): BASE_IMAGE (The customer)
        - Image 2 (The SECOND image): STYLE_IMAGE (The reference look)
        [PRIME DIRECTIVE - CRITICAL]:
        1. TARGET RECOGNITION: Focus ONLY on the human subject's head and body. Strictly ignore all mobile UI elements (status bars, notches, buttons, white/black bars) in both images.
        2. IDENTITY ANCHOR: Use Image 1 as the absolute anchor. Do NOT rotate, tilt, or distort the face. The eye-line, nose position, and head angle must be 100% identical to Image 1.
        3. STYLE EXTRACTION: Extract only the {mode} (texture, color, silhouette) from Image 2.
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
        
        response = model.generate_content([prompt, img_a, img_b])
        
        image_data = None
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_data = part.inline_data.data
                    break
        
        if image_data:
            # 워터마크 합성 로직 (폰트 합성 제외)
            base_image = Image.open(io.BytesIO(image_data)).convert("RGBA")
            logo = Image.open("logo.png").convert("RGBA")
            target_width = int(base_image.width * 0.2)
            aspect_ratio = logo.height / logo.width

            logo_resized = logo.resize((target_width, int(target_width * (logo.height/logo.width))), Image.LANCZOS)
            logo_resized.putalpha(128) # 0(투명) ~ 255(불투명) 중 중간값인 128 적용

            target_height = int(target_width * aspect_ratio)
            padding = 20
            position = (base_image.width - logo_resized.width - padding, base_image.height - logo_resized.height - padding)
            watermark_layer = Image.new('RGBA', base_image.size, (0,0,0,0))
            watermark_layer.paste(logo_resized, position, mask=logo_resized)
                    
            st.session_state.final_image = base_image # 결과물 저장
            st.session_state.styling_done = True
            return True
        return False
    except Exception as e:
        st.error(f"합성 엔진 오류: {e}")
        return False

# 1. 페이지 설정
st.set_page_config(page_title="헤나세르 가상 스타일링", layout="centered")
st.title("✂️ 헤나세르 가상 스타일링")

# 깔끔하게 메뉴와 푸터만 숨기기 (헤더 유지하여 키 입력창 보호)
st.markdown("""<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>""", unsafe_allow_html=True)

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

# 제미나이 설정
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
model = genai.GenerativeModel('nano-banana-pro-preview')

# --- [3. 메인 로직 시작] ---
# 액세스 키를 사이드바가 아닌 화면 최상단에 배치
st.markdown("### 🔑 멤버십 인증")
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
            st.markdown("### 👤 <span style='font-size: 24px;'>내 정면 사진 (Base)</span>", unsafe_allow_html=True)
            base_img_file = st.file_uploader("본인의 정면 사진", type=['jpg', 'png', 'jpeg'], label_visibility="collapsed")
            
            st.markdown("---")

            # 3. 합성할 헤어 사진 (Style) 섹션
            st.markdown("### 💇‍♂️ <span style='font-size: 24px;'>합성할 헤어 사진 (Style)</span>", unsafe_allow_html=True)
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
                st.markdown("---")
                # (1) 합성 사진
                st.image(st.session_state.final_image, use_column_width=True)

                # (2) 스타일 방향성 주의 문구
                st.markdown("""
                <div style='text-align: center; color: #808080; font-size: 13px; margin-top: 10px;'>
                    이 결과는 스타일 방향성을 보기 위한 AI 시뮬레이션입니다.<br>
                    실제와 100% 일치하지 않을 수 있습니다.
                </div>
                """, unsafe_allow_html=True)

                # (3) 좋아요 버튼
                st.write("")
                if st.button("👍 이 결과가 마음에 드시나요? (서비스 반영)"):
                    try:
                        current_likes_val = worksheet.cell(idx + 2, 4).value
                        current_likes = int(current_likes_val) if current_likes_val and str(current_likes_val).isdigit() else 0
                        worksheet.update_cell(idx + 2, 4, current_likes + 1)
                        st.toast("피드백 감사합니다! 😊")
                    except: pass

                # (4) 재합성 버튼 (확인창 없이 즉시 실행, 1회만 가능)
                if st.session_state.synthesis_count == 1:
                    st.write("")
                    if st.button("🔄 재합성 시도하기 (무료 1회)"):
                        with st.spinner("1~2분 정도 소요됩니다. 페이지를 이탈하거나 새로고침 하지 마세요."):
                            img_a = Image.open(base_img_file)
                            img_b = Image.open(style_img_file)
                            if run_synthesis(mode, img_a, img_b, idx, remaining):
                                st.session_state.synthesis_count = 2
                                st.rerun()

        else:
            st.error("잔여 횟수가 없습니다. 충전이 필요합니다.")
    else:
        st.error("잘못된 키입니다.")
else:
    st.info("계속하려면 인증 키를 입력해주세요.")