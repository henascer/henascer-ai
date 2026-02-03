import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
from PIL import Image, ImageOps, ImageDraw, ImageFont, ImageEnhance # ImageEnhance 추가
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


st.set_page_config(
    page_title="헤나세르 AI 스타일러",
    page_icon="logo.png", # 여기에 로고 파일을 지정하면 탭 로고가 바뀝니다.
    layout="centered"
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
            # 1. 원본 결과물 로드 (RGBA 모드)
            base_image = Image.open(io.BytesIO(image_data)).convert("RGBA")
            
            try:
                # 2. 로고 로드 및 설정
                logo = Image.open("logo.png").convert("RGBA")
                
                # 로고 크기 계산 (원본 너비의 15%)
                target_width = int(base_image.width * 0.15)
                aspect_ratio = logo.height / logo.width
                target_height = int(target_width * aspect_ratio)
                
                # 로고 리사이징 (깔끔한 품질을 위해 LANCZOS 필터 사용)
                logo_resized = logo.resize((target_width, target_height), Image.LANCZOS)
                
                # [핵심 수정] 투명도 조절 방식 변경 (스탬프 현상 해결)
                # putalpha 대신 알파 채널만 분리해서 강조(Enhance)하는 방식 사용
                alpha = logo_resized.split()[3] # RGBA 중 A(알파) 채널만 추출
                # 0.6은 투명도 60%를 의미합니다. (0.0 ~ 1.0 사이 조절 가능)
                alpha = ImageEnhance.Brightness(alpha).enhance(0.6) 
                logo_resized.putalpha(alpha) # 조절된 알파 채널을 다시 적용

                # 3. 로고 위치 계산 (우측 하단, 여백 30px)
                padding = 30
                position = (base_image.width - logo_resized.width - padding, 
                            base_image.height - logo_resized.height - padding)
                
                # mask=logo_resized 파라미터가 로고의 투명한 부분을 완벽하게 처리해줍니다.
                base_image.paste(logo_resized, position, mask=logo_resized)
                
                # 최종 결과물 저장 (다시 RGB로 변환)
                st.session_state.final_image = base_image.convert("RGB")
                
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

hide_streamlit_style = """
            <style>
            /* 1. 상단/하단 메뉴 전체 박멸 */
            header, footer {visibility: hidden !important; height: 0 !important; display: none !important;}
            #MainMenu {visibility: hidden !important;}
            .stAppDeployButton {display: none !important;}

            /* 2. 우측 하단 배지 및 프로필 이미지 (가장 강력한 저격) */
            /* 특정 클래스로 시작하는 모든 요소를 강제로 숨깁니다 */
            [class^="_container_"], [class^="_viewerBadge_"], [class^="_profileImage_"] {
                display: none !important;
                visibility: hidden !important;
                width: 0 !important;
                height: 0 !important;
            }

            /* 3. 데이터 테스크 아이디(보이지 않는 이름표) 저격 */
            [data-testid="stStatusWidget"], [data-testid="stToolbar"] {
                display: none !important;
            }

            /* 4. 화면을 감싸는 전체 레이아웃 여백 최적화 (로고가 있던 빈자리까지 제거) */
            .stApp {
                bottom: 0 !important;
            }
            #root > div:nth-child(1) > div.withScreencast > div > div > div > section > div.block-container {
                padding-bottom: 0rem !important;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

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
                # 모바일 하단 여백 추가 (버튼이 바닥에 붙지 않게 함)
                st.markdown("<div style='margin-bottom: 100px;'></div>", unsafe_allow_html=True)

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
                st.markdown("<div style='margin-bottom: 100px;'></div>", unsafe_allow_html=True)

        else:
            st.error("잔여 횟수가 없습니다. 충전이 필요합니다.")
    else:
        st.error("잘못된 키입니다.")
else:
    st.info("계속하려면 인증 키를 입력해주세요.")
    st.markdown("""
    <div style='background-color: #f1f3f5; padding: 20px; border-radius: 10px; border-left: 5px solid #adb5bd; margin-top: 10px;'>
        <p style='margin-bottom: 10px; font-weight: bold;'>📢 이용 공지사항</p>
        <ul style='font-size: 14px; color: #495057; padding-left: 20px;'>
            <li><b>코디 합성은 준비 중</b>이며, 추후 유료 서비스로 출시 예정입니다. (크레딧 제도 도입 예정)</li>
            <li>AI는 특성상 가끔 어색한 결과를 출력할 수 있어 <b>재합성 1회를 무료로 제공</b>합니다.</li>
            <li>재합성 시 기존 사진은 삭제되니, 결과가 마음에 드신다면 <b>반드시 먼저 캡쳐</b>해 주세요.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)